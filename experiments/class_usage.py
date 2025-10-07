class A:
    def __init__(self) -> None:
        self.counter = 0

    def increment(self, caller=None):
        self.counter += 1
        print(f"{self.counter=}" + f" from {caller}" if caller else "")


class B:
    def __init__(self, a: A, name: str) -> None:
        self.a = a
        self.name = name

    def do_stuff(self):
        self.a.increment(self.name)


def main():
    # python is indeed pass by reference
    a = A()
    b1 = B(a, "b1")
    b2 = B(a, "b2")
    b1.do_stuff()
    b2.do_stuff()
    b2.do_stuff()
    b1.do_stuff()
    pass


if __name__ == "__main__":
    main()
