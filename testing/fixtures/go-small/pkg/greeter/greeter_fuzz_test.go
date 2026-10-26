package greeter

import "testing"

// FuzzHello is a stub fuzz target for eval fixtures (fuzzing-test-generator).
func FuzzHello(f *testing.F) {
	f.Add("world")
	f.Fuzz(func(t *testing.T, name string) {
		_ = Greeter{}.Hello(name)
	})
}
