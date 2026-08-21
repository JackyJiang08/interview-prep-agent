"""Behavioral regression evaluation for the agent graph.

Scenario datasets freeze reference behavior — trajectories, state deltas,
outcomes — and evaluators score the real compiled graph against them, so a
future change that silently alters behavior turns the matrix red. Nothing
here measures output quality against labelled data.
"""
