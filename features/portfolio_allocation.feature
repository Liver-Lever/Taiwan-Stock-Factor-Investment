Feature: Rule-based portfolio allocation
  The MVP needs a transparent top-N baseline and a deterministic defensive tilt.

  Scenario: Top N stocks are equally weighted
    Given five ranked stocks
    When I select the top 3 stocks
    Then exactly 3 stocks each have one-third weight

  Scenario: Electronics are reduced and cash is redistributed
    Given a portfolio with 80 percent electronics and 20 percent non-electronics
    When electronic weights are reduced by 25 percent
    Then electronics total 60 percent and all weights sum to 100 percent

