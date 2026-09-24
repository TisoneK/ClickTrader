"""Browser-driven adapters: read a live site's DOM into the shapes `recording.py` expects.

Nothing in here places a trade. This is the shared foundation the recorder (layer 1) uses today and the
gated executor (layer 3) will reuse later for the click side, once a strategy has survived replay —
see DESIGN.md.

Playwright is an optional dependency (`pip install clicktrader[browser]`) so the core package and its
tests don't need a browser installed. Import submodules lazily where that matters.
"""
