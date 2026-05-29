"""Command modules for the AERIS CLI.

The commands package defines the user-facing command surface.

Keep this layer thin:
- parse CLI options
- perform light argument validation
- call pipeline/service functions
- print concise operator output

Do not put domain logic here.
"""