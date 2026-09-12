package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"unicode"
	"unicode/utf8"
)

type Symbol struct {
	Name      string `json:"name"`
	Kind      string `json:"kind"`
	Signature string `json:"signature"`
	Line      int    `json:"line"`
}

type Package struct {
	Name    string   `json:"name"`
	Path    string   `json:"path"`
	Symbols []Symbol `json:"symbols"`
}

type Result struct {
	Packages       []Package `json:"packages"`
	FuncComplexity []float64 `json:"func_complexity"`
	Errors         int       `json:"errors"`
}

type input struct {
	Files []string `json:"files"`
}

func isExported(name string) bool {
	r, _ := utf8.DecodeRuneInString(name)
	return unicode.IsUpper(r)
}

func cyclomatic(n ast.Node) float64 {
	d := 0
	ast.Inspect(n, func(x ast.Node) bool {
		switch x.(type) {
		case *ast.IfStmt, *ast.ForStmt, *ast.RangeStmt, *ast.CaseClause, *ast.CommClause:
			d++
		}
		return true
	})
	return float64(d + 1)
}

func extract(files []string) (Result, error) {
	fset := token.NewFileSet()
	byDir := map[string][]*ast.File{}
	pkgName := map[string]string{}
	errs := 0
	for _, f := range files {
		af, err := parser.ParseFile(fset, f, nil, 0)
		if err != nil {
			errs++
			continue
		}
		dir := filepath.Dir(f)
		byDir[dir] = append(byDir[dir], af)
		pkgName[dir] = af.Name.Name
	}
	var res Result
	res.Errors = errs
	for dir, filesAst := range byDir {
		pkg := Package{Name: pkgName[dir], Path: dir, Symbols: nil}
		for _, af := range filesAst {
			for _, decl := range af.Decls {
				switch d := decl.(type) {
				case *ast.FuncDecl:
					kind := "function"
					sig := "func " + d.Name.Name
					if d.Recv != nil {
						kind = "method"
					}
					line := fset.Position(d.Pos()).Line
					pkg.Symbols = append(pkg.Symbols, Symbol{Name: d.Name.Name, Kind: kind, Signature: sig, Line: line})
					res.FuncComplexity = append(res.FuncComplexity, cyclomatic(d))
				case *ast.GenDecl:
					for _, spec := range d.Specs {
						switch s := spec.(type) {
						case *ast.TypeSpec:
							kind := "type"
							if _, ok := s.Type.(*ast.InterfaceType); ok {
								kind = "interface"
							}
							if !isExported(s.Name.Name) {
								continue
							}
							line := fset.Position(s.Pos()).Line
							pkg.Symbols = append(pkg.Symbols, Symbol{Name: s.Name.Name, Kind: kind, Signature: kind + " " + s.Name.Name, Line: line})
						case *ast.ValueSpec:
							kind := "var"
							if d.Tok.String() == "const" {
								kind = "const"
							}
							for _, name := range s.Names {
								if !isExported(name.Name) {
									continue
								}
								line := fset.Position(name.Pos()).Line
								pkg.Symbols = append(pkg.Symbols, Symbol{Name: name.Name, Kind: kind, Signature: kind + " " + name.Name, Line: line})
							}
						}
					}
				}
			}
		}
		res.Packages = append(res.Packages, pkg)
	}
	return res, nil
}

func main() {
	var in input
	if err := json.NewDecoder(os.Stdin).Decode(&in); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	out, err := extract(in.Files)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
