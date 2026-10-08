"""Bounded declaration inspection for explicit source parameter names."""
from __future__ import annotations
import ast
from dataclasses import dataclass
from core.development.parameter_naming import ParameterNamingInspection, ParameterNamingMismatch

@dataclass(frozen=True)
class PythonParameterNaming:
    def missing_operations(self, request: ParameterNamingInspection) -> tuple[str, ...]:
        trees = [ast.parse(file.source) for file in request.files]
        missing = []
        for signature in request.signatures:
            bodies = [tree.body for tree in trees] if signature.owner is None else [
                node.body for tree in trees for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name == signature.owner]
            if not any(isinstance(node, ast.FunctionDef) and node.name == signature.name
                       for body in bodies for node in body):
                missing.append(signature.source_quote)
        return tuple(missing)

    def inspect(self, request: ParameterNamingInspection) -> tuple[ParameterNamingMismatch, ...]:
        trees = [ast.parse(file.source) for file in request.files]
        result: list[ParameterNamingMismatch] = []
        for signature in request.signatures:
            if signature.owner and sum(
                isinstance(node, ast.ClassDef) and node.name == signature.owner
                for tree in trees for node in tree.body
            ) > 1:
                raise ValueError("parameter naming requires one owning declaration")
            definitions: list[ast.FunctionDef] = []
            for tree in trees:
                bodies = [tree.body]
                if signature.owner:
                    bodies = [node.body for node in tree.body
                              if isinstance(node, ast.ClassDef) and node.name == signature.owner]
                definitions.extend(node for body in bodies for node in body
                                   if isinstance(node, ast.FunctionDef) and node.name == signature.name)
            if not definitions:
                continue  # Operation naming must be reconciled before its parameters.
            if len(definitions) != 1:
                raise ValueError("parameter naming requires one declaration")
            function = definitions[0]
            args = function.args
            names = tuple(arg.arg for arg in (*args.posonlyargs, *args.args))
            if signature.owner:
                names = names[1:]
            if len(names) != len(signature.parameters) or args.defaults or args.kwonlyargs or args.vararg or args.kwarg:
                raise ValueError("parameter naming cannot change call shape")
            result.extend(ParameterNamingMismatch(signature.owner,signature.name,index,current,required)
                          for index,(current,required) in enumerate(zip(names,signature.parameters))
                          if current != required)
        return tuple(result)
