# SPDX-License-Identifier: Apache-2.0 OR Commercial
"""Self-evolving pipeline gate registry.

Gates are assertions loaded from gates/registry.yaml and executed
by the golden pipeline test runner. Any external tool can add
gates via scripts/add_gate.py or by appending to the YAML directly.
"""
