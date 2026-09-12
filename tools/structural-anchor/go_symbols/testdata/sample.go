package sample

type Greeter struct{}

func (g Greeter) Hello(name string) string { return name }

func Add(a, b int) int {
	if a > 0 {
		return a + b
	}
	return b
}

type Face interface {
	Hello(string) string
}

const Exported = 1

var ExportedVar = 2
