from .operators import Operators, Operator


class GameData:
    operators = Operators()

    @classmethod
    def get_operator(cls, operator_name: str, operator_name_prefix: str = ''):
        opt: Operator | None = None

        if operator_name_prefix:
            opt = cls.operators.get_operator(operator_name_prefix + operator_name)

        if not opt:
            opt = cls.operators.get_operator(operator_name)
        else:
            operator_name = operator_name_prefix + operator_name

        return opt, operator_name

