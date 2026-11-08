Feature: Point-in-time factor calculation
  The stock-selection baseline must use five factors across at least three categories without future data.

  Scenario: Momentum ignores prices after the signal date
    Given a stock with steadily rising prices before and after the signal date
    When I calculate factors on the signal date
    Then changing future prices does not change its momentum

  Scenario: Lower volatility receives the higher defensive score
    Given two stocks with equal trend but different volatility
    When I calculate their factor scores
    Then the lower-volatility stock has the higher low-volatility score

  Scenario: Composite score contains all five required factors
    Given two stocks with equal trend but different volatility
    When I calculate their factor scores
    Then momentum, reversal, low-volatility, value and quality scores are present

