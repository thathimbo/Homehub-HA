"""Constants for the HomeHub integration."""
from datetime import timedelta

DOMAIN = "homehub"
SCAN_INTERVAL = timedelta(seconds=30)
# How far ahead the calendar entity looks for its next event
CALENDAR_LOOKAHEAD_DAYS = 30

SERVICE_ADD_EXPENSE = "add_expense"
INTENT_ADD_EXPENSE = "HomeHubAddExpense"
