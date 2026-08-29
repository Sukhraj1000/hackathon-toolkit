from canton8_hack.main import greet


def test_greet_default():
    assert greet() == "Hello, world! Welcome to canton8_hack."


def test_greet_custom_name():
    assert greet("Canton8") == "Hello, Canton8! Welcome to canton8_hack."
