User isolation fix included:
- current_portfolio_id now verifies the selected portfolio belongs to the logged-in user.
- Dashboard/analytics helper queries now defensively apply WHERE t.user_id = ? AND t.portfolio_id = ? if a caller forgets to pass filters.
- Tomorrow Trading Plan uses filtered_trade_rows from the current user/current portfolio only.
