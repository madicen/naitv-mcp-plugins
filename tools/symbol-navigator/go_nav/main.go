package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/printer"
	"go/token"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"
)

type Definition struct {
	Name      string   `json:"name"`
	Kind      string   `json:"kind"`
	File      string   `json:"file"`
	Line      int      `json:"line"`
	Column    int      `json:"column"`
	Signature string   `json:"signature"`
	Receivers []string `json:"receivers"`
	Imports   []string `json:"imports"`
}

type Reference struct {
	File    string `json:"file"`
	Line    int    `json:"line"`
	Column  int    `json:"column"`
	Context string `json:"context"`
}

type Location struct {
	File   string `json:"file"`
	Line   int    `json:"line"`
	Column int    `json:"column"`
}

type IndexResult struct {
	Defs   []Definition `json:"defs"`
	Errors int          `json:"errors"`
}

type RefsResult struct {
	References []Reference `json:"references"`
	Errors     int         `json:"errors"`
}

type input struct {
	Mode    string     `json:"mode"`
	Symbol  string     `json:"symbol"`
	Files   []string   `json:"files"`
	Exclude []Location `json:"exclude"`
}

func nodeString(fset *token.FileSet, node any) string {
	var out bytes.Buffer
	if err := printer.Fprint(&out, fset, node); err != nil {
		return ""
	}
	return out.String()
}

func receiverName(fset *token.FileSet, decl *ast.FuncDecl) string {
	if decl.Recv == nil || len(decl.Recv.List) == 0 {
		return ""
	}
	return nodeString(fset, decl.Recv.List[0].Type)
}

func funcSignature(fset *token.FileSet, decl *ast.FuncDecl) string {
	funcType := strings.TrimPrefix(nodeString(fset, decl.Type), "func")
	if receiver := receiverName(fset, decl); receiver != "" {
		return "func (" + receiver + ") " + decl.Name.Name + funcType
	}
	return "func " + decl.Name.Name + funcType
}

func importsFor(file *ast.File) []string {
	imports := make([]string, 0, len(file.Imports))
	for _, spec := range file.Imports {
		path, err := strconv.Unquote(spec.Path.Value)
		if err == nil {
			imports = append(imports, path)
		}
	}
	sort.Strings(imports)
	return imports
}

func isExported(name string) bool {
	r, _ := utf8.DecodeRuneInString(name)
	return unicode.IsUpper(r)
}

func absolute(path string) string {
	abs, err := filepath.Abs(path)
	if err != nil {
		return path
	}
	return abs
}

func Index(files []string) IndexResult {
	out := IndexResult{Defs: []Definition{}}
	for _, path := range files {
		path = absolute(path)
		fset := token.NewFileSet()
		file, err := parser.ParseFile(fset, path, nil, 0)
		if err != nil {
			out.Errors++
			continue
		}
		imports := importsFor(file)
		add := func(name, kind, signature string, pos token.Pos, receivers []string) {
			position := fset.Position(pos)
			out.Defs = append(out.Defs, Definition{
				Name: name, Kind: kind, File: path, Line: position.Line,
				Column: position.Column, Signature: signature,
				Receivers: receivers, Imports: append([]string{}, imports...),
			})
		}
		for _, declaration := range file.Decls {
			switch decl := declaration.(type) {
			case *ast.FuncDecl:
				kind := "function"
				receivers := []string{}
				if receiver := receiverName(fset, decl); receiver != "" {
					kind = "method"
					receivers = append(receivers, receiver)
				}
				add(decl.Name.Name, kind, funcSignature(fset, decl), decl.Name.Pos(), receivers)
			case *ast.GenDecl:
				for _, specification := range decl.Specs {
					switch spec := specification.(type) {
					case *ast.TypeSpec:
						kind := "type"
						if _, ok := spec.Type.(*ast.InterfaceType); ok {
							kind = "interface"
						}
						add(spec.Name.Name, kind, "type "+spec.Name.Name+" "+nodeString(fset, spec.Type), spec.Name.Pos(), []string{})
					case *ast.ValueSpec:
						kind := decl.Tok.String()
						if kind != "const" && kind != "var" {
							continue
						}
						for _, name := range spec.Names {
							if isExported(name.Name) {
								add(name.Name, kind, kind+" "+name.Name, name.Pos(), []string{})
							}
						}
					}
				}
			}
		}
	}
	sort.Slice(out.Defs, func(i, j int) bool {
		a, b := out.Defs[i], out.Defs[j]
		if a.File != b.File {
			return a.File < b.File
		}
		if a.Line != b.Line {
			return a.Line < b.Line
		}
		if a.Column != b.Column {
			return a.Column < b.Column
		}
		return a.Name < b.Name
	})
	return out
}

func Refs(symbol string, files []string, exclude []Location) RefsResult {
	out := RefsResult{References: []Reference{}}
	type span struct {
		line, column int
	}
	excluded := map[string]map[span]bool{}
	for _, location := range exclude {
		path := absolute(location.File)
		if excluded[path] == nil {
			excluded[path] = map[span]bool{}
		}
		excluded[path][span{location.Line, location.Column}] = true
	}
	for _, path := range files {
		path = absolute(path)
		source, err := os.ReadFile(path)
		if err != nil {
			out.Errors++
			continue
		}
		fset := token.NewFileSet()
		file, err := parser.ParseFile(fset, path, source, 0)
		if err != nil {
			out.Errors++
			continue
		}
		lines := strings.Split(string(source), "\n")
		ast.Inspect(file, func(node ast.Node) bool {
			ident, ok := node.(*ast.Ident)
			if !ok || ident.Name != symbol {
				return true
			}
			position := fset.Position(ident.Pos())
			if excluded[path][span{position.Line, position.Column}] {
				return true
			}
			context := ""
			if position.Line > 0 && position.Line <= len(lines) {
				context = strings.TrimSpace(lines[position.Line-1])
			}
			out.References = append(out.References, Reference{
				File: path, Line: position.Line, Column: position.Column, Context: context,
			})
			return true
		})
	}
	sort.Slice(out.References, func(i, j int) bool {
		a, b := out.References[i], out.References[j]
		if a.File != b.File {
			return a.File < b.File
		}
		if a.Line != b.Line {
			return a.Line < b.Line
		}
		return a.Column < b.Column
	})
	return out
}

func main() {
	var in input
	if err := json.NewDecoder(os.Stdin).Decode(&in); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}

	var out any
	switch in.Mode {
	case "index":
		out = Index(in.Files)
	case "refs":
		out = Refs(in.Symbol, in.Files, in.Exclude)
	default:
		fmt.Fprintf(os.Stderr, "unsupported mode %q\n", in.Mode)
		os.Exit(1)
	}
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
