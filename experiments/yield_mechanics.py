def fu():
    print("yielding 1 from fu")
    yield 1


print("the simplest generator function:")
next(fu())
next(fu())
next(fu())


def func(iterations: int):
    try:
        for i in range(iterations):
            signal = yield i
            print(f"sent: {i} | received: {signal}")
        return "Hidden Secret Message!"
    except ValueError as e:
        print(f"catching error: {e.args[0]!r}")
        yield -1


gen = func(3)
print("\ncalling next...")
next(gen)
print("depleting func with for loop:")
for i in gen:
    pass

gen = func(5)
print("\ndepleting func with while loop:")
i = 0
while True:
    try:
        if i % 2:
            i = gen.send("hello world")
        else:
            i = next(gen)
    except StopIteration:
        break


def funcfunc():
    hidden_message = yield from func(3)
    print(f"We got it boys: {hidden_message!r}")


print("\ndepleting funcfunc with while loop:")
for _ in funcfunc():
    pass
print("\nextracting return form func with while loop:")

gen = func(3)
while True:
    try:
        next(gen)
    except StopIteration as e:
        # NOTE: Only StopIteration and StopAsyncIteration have .value
        print(f"Got it, but clunkier: {e.value!r}")
        break

print("\nsending exceptions into func:")
gen = func(5)
i = 0
while True:
    if i == -1:
        print(f"received {i} from func, breaking")
        break
    step = i % 3
    if step == 0:
        i = next(gen)
    elif step == 1:
        i = gen.send("hello world")
    else:
        i = gen.throw(ValueError("catch this!"))


def funcy():
    try:
        while True:
            print("funcy yielding 1")
            msg = yield 1
            if msg == -1:
                print(f"received: {msg} | funcy yielding 2")
                yield 2
    except GeneratorExit as e:
        print(f"funcy is sad, funcy was asked to .close()")
    finally:
        print("finally block, let's try to yield after GeneratorExit!")
        yield "should not have done that"


print("\ntesting funcy with GeneratorExit handling:")
gen = funcy()
next(gen)
next(gen)
gen.send(-1)
next(gen)
next(gen)
try:
    gen.close()
except RuntimeError:
    print("main execution block forgives funcy for yielding after close")
