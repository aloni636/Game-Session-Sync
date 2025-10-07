class A:
    def __init__(self) -> None:
        self.mutable = {"value": 1}


class B(A):
    def __init__(self, name) -> None:
        super().__init__()
        self.name = name

    def increment(self):
        self.mutable["value"] += 1
        print(f"{self.name}: {self.mutable}")


class C(A):
    def __init__(self, name) -> None:
        super().__init__()
        self.name = name

    def increment(self):
        self.mutable["value"] += 1
        print(f"{self.name}: {self.mutable}")


if __name__ == "__main__":
    b = B("b")
    c = C("c")
    b.increment()
    c.increment()
