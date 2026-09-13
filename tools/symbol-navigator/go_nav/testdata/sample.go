package sample

type UserService struct{}

func (u UserService) Hello() string { return "hi" }

func NewUserService() *UserService { return &UserService{} }

const ExportedConst = "value"

var ExportedVar = 1
