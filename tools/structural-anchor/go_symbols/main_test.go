package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestExtractSample(t *testing.T) {
	path := filepath.Join("testdata", "sample.go")
	abs, _ := filepath.Abs(path)
	out, err := extract([]string{abs})
	if err != nil {
		t.Fatal(err)
	}
	if len(out.Packages) == 0 {
		t.Fatal("no packages")
	}
	kinds := map[string]string{}
	for _, s := range out.Packages[0].Symbols {
		kinds[s.Name] = s.Kind
	}
	if kinds["Add"] != "function" || kinds["Hello"] != "method" {
		t.Fatalf("kinds=%v", kinds)
	}
	if kinds["Greeter"] != "type" || kinds["Face"] != "interface" {
		t.Fatalf("types=%v", kinds)
	}
	if kinds["Exported"] != "const" || kinds["ExportedVar"] != "var" {
		t.Fatalf("vars=%v", kinds)
	}
	_ = json.NewEncoder(os.Stdout)
}
