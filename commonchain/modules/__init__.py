"""Optional domain modules for commonchain.

Each module is a pilot example of organisation-specific functionality plugged
into the universal decision-record core. Modules never change the core's
guarantees (soulbound stakes, one-member-one-vote, hash-linked memory); they
only read core state and add their own computations.

Available modules:
    payroll -- revenue sharing for companies and co-ops.
"""

__all__: list[str] = []
