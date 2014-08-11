import operator as op
from parsimonious.grammar import Grammar


# Parsers for Checklist Verification

class Evaluator(object):
    def __init__(self, env={}):
        self.env = env
        self.scratch = None  # for storing temporary results

    def parse(self, source):
        grammar = '\n'.join(v.__doc__ for k, v in vars(self.__class__).items()
                            if '__' not in k and hasattr(v, '__doc__')
                            and v.__doc__)
        return Grammar(grammar).parse(source)

    def eval(self, source):
        node = self.parse(source) if isinstance(source, str) \
            or isinstance(source, unicode) else source
        method = getattr(self, node.expr_name, lambda node, children: children)
        return method(node, [self.eval(n) for n in node])

    def expr(self, node, children):
        'expr = operand operation*'
        operand, operation = children
        self.scratch = None
        try:
            return children[1][-1]
        except IndexError:
            return operand

    def operand(self, node, children):
        'operand = _ (variable / number) _'
        _, value, _ = children
        if self.scratch is None:
            self.scratch = value[0]
        return value[0]

    def operation(self, node, children):
        'operation = operator operand'
        operator, operand = children
        self.scratch = operator(self.scratch, operand)
        return self.scratch

    def operator(self, node, children):
        'operator = "+" / "-" / "*" / "/"'
        operators = {'+': op.add, '-': op.sub, '*': op.mul, '/': op.div}
        return operators[node.text]

    def variable(self, node, children):
        'variable = ~"[a-z]+"i _'
        try:
            return float(getattr(self.env, node.text.strip(), 0))
        except TypeError:
            return 0

    def number(self, node, children):
        'number = ~"\-?[0-9\.]+"'
        return float(node.text)

    def _(self, node, children):
        '_ = ~"\s*"'
        pass


class Comparator(object):
    def __init__(self):
        self.param = None

    def parse(self, source):
        grammar = '\n'.join(v.__doc__ for k, v in vars(self.__class__).items()
                            if '__' not in k and hasattr(v, '__doc__')
                            and v.__doc__)
        return Grammar(grammar).parse(source)

    def eval(self, source, param=None):
        if param is not None:
            self.param = float(param)
        node = self.parse(source) if isinstance(source, str) \
            or isinstance(source, unicode) else source
        method = getattr(self, node.expr_name, lambda node, children: children)
        return method(node, [self.eval(n) for n in node])

    def expr(self, node, children):
        'expr = operator _ number'
        operator, _, number = children
        return operator(self.param, number)

    def operator(self, node, children):
        'operator = ">=" / "<=" / ">" / "<" / "="'
        operators = {
            '>': op.gt, '>=': op.ge, '<': op.lt, '<=': op.le, '=': op.eq}
        return operators[node.text]

    def number(self, node, children):
        'number = ~"\-?[0-9\.]+"'
        return float(node.text)

    def _(self, node, children):
        '_ = ~"\s*"'
        pass
