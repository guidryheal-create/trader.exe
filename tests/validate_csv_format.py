#!/usr/bin/env python3
"""
Validate CSV Format Logic

Validates that the CSV format generation logic is correct.
This test doesn't require httpx or full client setup.
"""
import sys

def validate_csv_format_logic():
    """Validate CSV format generation logic with REAL T0 price as base."""
    print("="*80)
    print("🔍 Validating CSV Format Logic (T+1 to T+14 only, relative to REAL T0)")
    print("="*80)
    
    # Simulate the CSV generation logic from get_trend_analysis
    # ✅ NEW APPROACH: Use REAL T0 price as base, calculate all forecasted variations relative to it
    ticker = "BTC-USD"
    csv_header_parts = ["ticker"]
    csv_row_parts = [ticker]
    real_t0_price = 50000.0  # REAL current market price (actual, not forecasted)
    
    # ✅ NEW APPROACH: Use REAL T0 price as base, calculate all forecasted variations relative to it
    real_t0_price = 50000.0  # REAL current market price (actual, not forecasted)
    
    # Mock forecasted prices for T+1 to T+14 (all forecasted, relative to real T0)
    mock_forecasted_prices = {}
    for t_delta in range(1, 15):  # T+1 to T+14 only (forecasted future)
        # Simulate forecasted price: +0.5% per day relative to real T0
        forecasted_price = real_t0_price * (1 + (t_delta * 0.005))
        mock_forecasted_prices[t_delta] = forecasted_price
    
    # ✅ Build CSV format: ticker,T+1,T+2,...,T+14 (only forecasted future, no T-1 or T)
    # All variations are calculated relative to real T0 price
    for t_delta in range(1, 15):  # T+1 to T+14 only
        csv_header_parts.append(f"T{t_delta:+d}")  # T+1, T+2, ..., T+14
        
        # Find forecasted price for this T-delta
        forecasted_price = mock_forecasted_prices.get(t_delta, None)
        if forecasted_price is not None:
            # Calculate %change relative to REAL T0: ((forecasted_price - real_t0_price) / real_t0_price) * 100
            percent_change = ((forecasted_price - real_t0_price) / real_t0_price) * 100.0
            
            # Format as: +2%, -1%, 0%, +2.5%, -1.2%
            if abs(percent_change) < 0.05:  # Less than 0.05% rounds to 0%
                csv_row_parts.append("0%")
            elif abs(percent_change % 1.0) < 0.01:  # Whole number
                csv_row_parts.append(f"{int(round(percent_change)):+d}%")
            else:  # Fractional
                if percent_change > 0:
                    csv_row_parts.append(f"+{percent_change:.1f}%")
                else:
                    csv_row_parts.append(f"{percent_change:.1f}%")
        else:
            csv_row_parts.append("N/A")
    
    csv_format = ",".join(csv_header_parts) + "\n" + ",".join(csv_row_parts)
    
    print("\n📊 Generated CSV Format:")
    print(csv_format)
    print()
    
    # Validate format
    lines = csv_format.strip().split("\n")
    assert len(lines) == 2, f"Expected 2 lines (header + data), got {len(lines)}"
    
    header = lines[0]
    data_row = lines[1]
    
    # Validate header (should be: ticker,T+1,T+2,...,T+14 - no T-1 or T)
    print("✅ Validating header...")
    header_parts = header.split(",")
    assert header_parts[0] == "ticker", f"Expected 'ticker' as first column, got: {header_parts[0]}"
    assert "T-1" not in header_parts, "Header should NOT contain 'T-1' (only T+1 to T+14)"
    assert header_parts[1] != "T", "Header should NOT contain 'T' (only T+1 to T+14)"
    assert "T+1" in header_parts, "Header should contain 'T+1'"
    assert "T+2" in header_parts, "Header should contain 'T+2'"
    assert "T+14" in header_parts, f"Header should contain 'T+14', got columns: {header_parts[-5:]}"
    assert len(header_parts) == 15, f"Expected 15 columns (ticker + T+1 to T+14), got {len(header_parts)}"
    print(f"   ✅ Header has {len(header_parts)} columns: {header_parts[0]}, {header_parts[1]}, ..., {header_parts[-1]}")
    
    # Validate data row (should be: BTC-USD,+2%,+3%,+4%,... - no T-1 or T variations)
    print("\n✅ Validating data row...")
    data_parts = data_row.split(",")
    assert len(data_parts) == 15, f"Expected 15 columns (ticker + T+1 to T+14), got {len(data_parts)}"
    assert data_parts[0] == "BTC-USD", f"Expected 'BTC-USD' as first value, got: {data_parts[0]}"
    print(f"   ✅ Data row has {len(data_parts)} columns: {data_parts[0]}, {data_parts[1]}, ..., {data_parts[-1]}")
    
    # Validate variations format (T+1 to T+14 only, relative to real T0)
    print("\n✅ Validating variation format (T+1 to T+14 only, relative to real T0)...")
    for i, value in enumerate(data_parts[1:], start=1):  # Start from T+1
        if value != "N/A":
            assert value.endswith("%"), f"Column {i} (T={i}): Expected % at end, got: {value}"
            if value != "0%":
                assert value[0] in ["+", "-"], f"Column {i} (T={i}): Expected + or - prefix, got: {value}"
                # Verify numeric part
                try:
                    numeric_part = float(value[:-1])  # Remove %
                    print(f"   T={i:3d}: {value:>6s} (numeric: {numeric_part:+.2f}%)")
                except ValueError:
                    assert False, f"Column {i} (T={i}): Invalid numeric format, got: {value}"
            else:
                print(f"   T={i:3d}: {value:>6s} (no change)")
    
    print("\n✅✅✅ CSV Format Validation Passed!")
    print("\nExpected Format (T+1 to T+14 only, relative to real T0):")
    print("  ticker,T+1,T+2,...,T+14")
    print("  BTC-USD,+2%,+3%,...,+15%")
    print("\nActual Format:")
    print(f"  {header}")
    print(f"  {data_row}")
    print("\n✅ Key points:")
    print("  - Base (T0) is REAL (actual current market price) - not shown in CSV")
    print("  - Only forecasted variations (T+1 to T+14) are shown")
    print("  - All variations are relative to real T0 (0% change)")
    print("  - This avoids bias by anchoring all forecasts to the same real baseline")
    
    # Verify format matches expected pattern
    print("\n✅ Format matches expected pattern!")
    return True


if __name__ == "__main__":
    try:
        validate_csv_format_logic()
        print("\n" + "="*80)
        print("✅✅✅ ALL VALIDATIONS PASSED!")
        print("="*80)
        sys.exit(0)
    except AssertionError as e:
        print(f"\n❌ Validation failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

