package main

import (
	"path/filepath"
	"reflect"
	"testing"
)

func testFiles(t *testing.T) []string {
	t.Helper()
	files := []string{
		filepath.Join("testdata", "user.go"),
		filepath.Join("testdata", "sample.go"),
	}
	for i, file := range files {
		abs, err := filepath.Abs(file)
		if err != nil {
			t.Fatal(err)
		}
		files[i] = abs
	}
	return files
}

func TestIndexFindsDefinitionsWithMethodReceiver(t *testing.T) {
	out := Index(testFiles(t))
	if out.Errors != 0 {
		t.Fatalf("errors=%d", out.Errors)
	}

	defs := map[string]Definition{}
	for _, def := range out.Defs {
		defs[def.Name] = def
	}
	if defs["UserService"].Kind != "type" {
		t.Fatalf("UserService=%+v", defs["UserService"])
	}
	if defs["Hello"].Kind != "method" {
		t.Fatalf("Hello=%+v", defs["Hello"])
	}
	if got := defs["Hello"].Signature; got != "func (UserService) Hello() string" {
		t.Fatalf("Hello signature=%q", got)
	}
	if defs["ExportedConst"].Kind != "const" || defs["ExportedVar"].Kind != "var" {
		t.Fatalf("exported values: const=%+v var=%+v", defs["ExportedConst"], defs["ExportedVar"])
	}

	for i := 1; i < len(out.Defs); i++ {
		prev, next := out.Defs[i-1], out.Defs[i]
		if prev.File > next.File || (prev.File == next.File && prev.Line > next.Line) {
			t.Fatalf("definitions not sorted: %+v before %+v", prev, next)
		}
	}
}

func TestRefsFindsUsesAndHonorsExclusions(t *testing.T) {
	files := testFiles(t)
	index := Index(files)
	def := func(name string) Definition {
		t.Helper()
		for _, item := range index.Defs {
			if item.Name == name {
				return item
			}
		}
		t.Fatalf("definition %q not found", name)
		return Definition{}
	}

	hello := def("Hello")
	out := Refs("Hello", files, []Location{{File: hello.File, Line: hello.Line}})
	if out.Errors != 0 {
		t.Fatalf("errors=%d", out.Errors)
	}
	if len(out.References) != 1 || out.References[0].Line != 6 ||
		out.References[0].Context != "_ = s.Hello()" {
		t.Fatalf("Hello references=%+v", out.References)
	}

	service := def("UserService")
	out = Refs("UserService", files, []Location{{File: service.File, Line: service.Line}})
	got := make([]int, len(out.References))
	for i, ref := range out.References {
		got[i] = ref.Line
	}
	if want := []int{5, 7, 7, 5}; !reflect.DeepEqual(got, want) {
		t.Fatalf("UserService lines=%v, want %v", got, want)
	}
}
