"""
Test cases for evaluating the Data Agent.

Each test is (question, expected_values, category).
Expected values are strings that should appear in the response.
"""

# (question, expected_values, category)
TEST_CASES = [
    # Basic
    ("Who won the most races in 2019?", ["Lewis Hamilton", "11"], "basic"),
    ("Which team won the 2020 constructors championship?", ["Mercedes"], "basic"),
    ("Who won the 2020 drivers championship?", ["Lewis Hamilton"], "basic"),
    ("How many races were there in 2019?", ["21"], "basic"),
    # Aggregation
    ("Which driver has won the most world championships?", ["Michael Schumacher", "7"], "aggregation"),
    ("Which constructor has won the most championships?", ["Ferrari"], "aggregation"),
    ("Who has the most fastest laps at Monaco?", ["Michael Schumacher"], "aggregation"),
    ("How many race wins does Lewis Hamilton have in total?", ["Hamilton"], "aggregation"),
    ("Which team has the most race wins all time?", ["Ferrari"], "aggregation"),
    # Data quality (tests type handling)
    ("Who finished second in the 2019 drivers championship?", ["Valtteri Bottas"], "data_quality"),
    ("Which team came third in the 2020 constructors championship?", ["Racing Point"], "data_quality"),
    ("How many races did Ferrari win in 2019?", ["3"], "data_quality"),
    # Complex
    ("Compare Ferrari vs Mercedes championship points from 2015-2020", ["Ferrari", "Mercedes"], "complex"),
    ("Who had the most podium finishes in 2019?", ["Lewis Hamilton"], "complex"),
    ("Which driver won the most races for Ferrari?", ["Michael Schumacher"], "complex"),
]

CATEGORIES = ["basic", "aggregation", "data_quality", "complex"]
