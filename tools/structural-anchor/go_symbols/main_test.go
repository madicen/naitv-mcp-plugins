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
	signatures := map[string]string{}
	for _, s := range out.Packages[0].Symbols {
		kinds[s.Name] = s.Kind
		signatures[s.Name] = s.Signature
	}
	if kinds["Add"] != "function" || kinds["Hello"] != "method" {
		t.Fatalf("kinds=%v", kinds)
	}
	if signatures["Hello"] != "func (Greeter) Hello(name string) string" {
		t.Fatalf("Hello signature=%q", signatures["Hello"])
	}
	if kinds["Greeter"] != "type" || kinds["Face"] != "interface" {
		t.Fatalf("types=%v", kinds)
	}
	if kinds["Exported"] != "const" || kinds["ExportedVar"] != "var" {
		t.Fatalf("vars=%v", kinds)
	}
	_ = json.NewEncoder(os.Stdout)
}
