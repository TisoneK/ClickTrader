"""API-driven adapters: a documented feed instead of a scraped page.

Where `clicktrader.browser` reads a site's DOM because no API is offered, this reads a real, documented
protocol directly. Deriv's WebSocket API is the first of these — see `deriv.py`.
"""
