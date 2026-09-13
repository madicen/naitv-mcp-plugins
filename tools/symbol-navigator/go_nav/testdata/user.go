package sample

func Use() {
	_ = NewUserService()
	var s UserService
	_ = s.Hello()
}
