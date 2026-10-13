package greeter

const ExportedConst = 1
const unexportedConst = 2

var ExportedVar = "ok"
var unexportedVar = "no"

type Greeter struct{}

func (g Greeter) Hello(name string) string {
	return "hi " + name
}

func Add(a, b int) int {
	return a + b
}

func unexportedFn() {}
