Feature: Point-in-time data and transaction costs
  The backtest must reject future snapshots and report net returns.

  Scenario: Future constituent snapshot is unavailable
    Given one published snapshot and one future snapshot
    When I request constituents before the future publication date
    Then only the published snapshot is returned

  Scenario: Transaction costs reduce net return
    Given a fully invested one-period portfolio
    When I backtest with positive transaction costs
    Then net return is lower than gross return

