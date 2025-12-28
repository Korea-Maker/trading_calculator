"""
Binance USDT-M 선물 트레이딩 계산기 웹 애플리케이션
"""

import streamlit as st
import pandas as pd
from trading_calculator import calculate_trading_results, TradingInputs


def format_currency(value: float) -> str:
    """통화 포맷"""
    return f"${value:,.2f}"


def format_percent(value: float) -> str:
    """퍼센트 포맷"""
    return f"{value:.2f}%"


def format_number(value: float, decimals: int = 2) -> str:
    """숫자 포맷"""
    return f"{value:,.{decimals}f}"


def create_results_table(results, inputs: TradingInputs) -> pd.DataFrame:
    """결과 표 생성 (동적 익절가 처리)"""
    items = [
        "1. 손절 폭 (%)",
        "1. 손절가",
        "1. 실제 손실 금액",
        "2. 적정 포지션 크기 (Notional)",
        "2. 적정 포지션 수량",
        "3. 포지션 사용 레버리지",
        "3. 실질 레버리지",
    ]
    
    values = [
        format_percent(results.stop_loss_pct),
        format_currency(results.stop_loss_price),
        format_currency(results.actual_loss_amount),
        format_currency(results.position_notional),
        format_number(results.position_quantity, 6),
        f"{results.position_leverage:.2f}x",
        f"{results.effective_leverage:.2f}x",
    ]
    
    # 동적 익절가 결과 추가
    for tp_num in sorted(results.take_profit_results.keys()):
        tp_result = results.take_profit_results[tp_num]
        items.extend([
            f"4. {tp_num}차 손익비 (R/R)",
            f"4. 실제 {tp_num}차 손익비",
            f"4. {tp_num}차 익절 시 순이익"
        ])
        values.extend([
            f"{tp_result['rr_ratio']:.2f}",
            f"{tp_result['actual_rr']:.2f}",
            format_currency(tp_result['profit'])
        ])
    
    # 나머지 항목 추가
    items.extend([
        "5. 구조적 문제 여부",
        "6. 필요 Margin",
        "7. 종합 판정",
        "8. 실제 진입 Notional",
        "8. 실제 진입 수량",
        "8. 실제 진입 레버리지"
    ])
    
    values.extend([
        results.structural_issue,
        format_currency(results.required_margin),
        results.overall_judgment,
        format_currency(results.actual_entry_notional),
        format_number(results.actual_entry_quantity, 6),
        f"{results.actual_entry_leverage:.2f}x"
    ])
    
    return pd.DataFrame({"항목": items, "값": values})


def generate_alert_message(results, inputs: TradingInputs) -> str:
    """Alert 메시지 생성 (동적 익절가 처리)"""
    direction_symbol = "📈 LONG" if inputs.direction == "LONG" else "📉 SHORT"
    
    # 익절가 동적 생성
    tp_lines = []
    for idx, tp in enumerate(inputs.take_profits, start=1):
        tp_lines.append(f"• TP{idx} : {tp:.2f}")
    
    tp_section = "\n".join(tp_lines)
    
    message = f"""{direction_symbol} SETUP
• Entry : {inputs.entry_price:.2f}
• Margin : {results.required_margin:.2f}
{tp_section}
• SL : {inputs.stop_loss:.2f}
• Leverage : {results.actual_entry_leverage:.2f}x"""
    
    return message


def main():
    st.set_page_config(
        page_title="Binance USDT-M 선물 계산기",
        page_icon="📊",
        layout="wide"
    )
    
    st.title("📊 Binance USDT-M 선물 트레이딩 계산기")
    st.markdown("---")
    
    # 입력 폼
    col1, col2 = st.columns(2)
    
    with col1:
        total_asset = st.number_input(
            "총 자산 ($)",
            min_value=0.0,
            value=10000.0,
            step=100.0,
            format="%.2f"
        )
        
        risk_ratio = st.slider(
            "최대 리스크 비율 (총 자산 기반) (%)",
            min_value=5.0,
            max_value=20.0,
            value=5.0,
            step=0.5
        )
        
        margin_usage_ratio = st.number_input(
            "사용 가능 Margin 비율 (총 자산 대비) (%)",
            min_value=1.0,
            max_value=100.0,
            value=60.0,
            step=5.0,
            format="%.1f",
            help="총 자산 대비 사용할 Margin 비율 (예: 60% = 총 자산 $300에서 $180를 Margin으로 사용)"
        )
        
        direction = st.selectbox(
            "포지션 방향",
            options=["LONG", "SHORT"]
        )
    
    with col2:
        entry_price = st.number_input(
            "진입가",
            min_value=0.0,
            value=50000.0,
            step=1.0,
            format="%.2f"
        )
        
        stop_loss = st.number_input(
            "스탑 로스",
            min_value=0.0,
            value=49000.0,
            step=1.0,
            format="%.2f"
        )
    
    st.markdown("---")
    st.subheader("익절가 설정")
    
    # 익절가 개수 선택
    num_take_profits = st.number_input(
        "익절가 개수",
        min_value=1,
        max_value=10,
        value=2,
        step=1,
        help="1차만 설정하거나 최대 10차까지 설정할 수 있습니다"
    )
    
    # 동적 익절가 입력 필드
    take_profits = []
    if num_take_profits > 0:
        # 3열로 배치
        num_cols = 3
        for i in range(0, num_take_profits, num_cols):
            cols = st.columns(num_cols)
            for j in range(num_cols):
                if i + j < num_take_profits:
                    with cols[j]:
                        tp_value = st.number_input(
                            f"{i+j+1}차 익절",
                            min_value=0.0,
                            value=51000.0 + ((i+j) * 1000.0),
                            step=1.0,
                            format="%.2f",
                            key=f"tp_{i+j}"
                        )
                        take_profits.append(tp_value)
    
    st.markdown("---")
    
    # 계산 버튼
    if st.button("계산하기", type="primary", use_container_width=True):
        try:
            # 입력값 검증
            if not take_profits:
                st.error("최소 1개의 익절가를 입력해주세요.")
                return
            
            inputs = TradingInputs(
                total_asset=total_asset,
                risk_ratio=risk_ratio,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profits=take_profits,
                margin_usage_ratio=margin_usage_ratio
            )
            
            # 계산 수행
            results = calculate_trading_results(inputs)
            
            # 결과 표시
            st.subheader("📋 계산 결과")
            results_df = create_results_table(results, inputs)
            st.dataframe(results_df, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            
            # Alert 메시지
            st.subheader("🔔 Alert 메시지")
            alert_message = generate_alert_message(results, inputs)
            st.code(alert_message, language=None)
            
            # 복사 버튼
            st.button("메시지 복사", key="copy_alert", use_container_width=True)
            
        except Exception as e:
            st.error(f"계산 중 오류가 발생했습니다: {str(e)}")
            st.exception(e)
    
    # 안내 사항
    with st.expander("ℹ️ 사용 안내"):
        st.markdown("""
        - **Binance USDT-M 선물** 기준으로 계산됩니다
        - **Isolated Margin** 모드입니다
        - **Taker 수수료 (0.04% 왕복)**가 포함됩니다
        - 리스크 비율을 최우선으로 포지션 사이즈를 산출합니다
        - 레버리지는 3~150배 범위 내에서 자동으로 계산됩니다
        """)


if __name__ == "__main__":
    main()

