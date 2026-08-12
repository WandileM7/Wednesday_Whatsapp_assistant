"""Scripted conversation evals against a real model.

`tests/` proves the machinery is wired correctly with a fake Ollama. This
package measures whether the assistant is any *good* — persona, routing,
memory recall, surface discipline — which needs real inference and so cannot
live in the unit suite.
"""
