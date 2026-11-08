Feature: Month-end signal timing and hysteresis
  A close-based signal must not be traded before it becomes observable.

  Scenario: Month-end signal trades on the next trading day
    Given trading days spanning two month ends
    When I build monthly rebalance events
    Then every execution date is later than its signal date

  Scenario: A reading inside the band retains the weak state
    Given an electronic index that first falls below and then enters the hysteresis band
    When I classify month-end regimes with a 2 percent band
    Then the second signal remains weak

