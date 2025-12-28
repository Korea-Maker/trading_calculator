"""
Binance USDT-M 선물 트레이딩 계산기
Isolated Margin, Taker 수수료 포함
함수형 프로그래밍 방식
"""

from typing import Tuple, Literal, List, Dict
from dataclasses import dataclass, field


# 상수 정의
TAKER_FEE_RATE = 0.0004  # Taker 수수료 0.04% (왕복)
MIN_LEVERAGE = 3
MAX_LEVERAGE = 150
PREFERRED_LEVERAGE_RANGE = (3, 150)


@dataclass
class TradingInputs:
    """트레이딩 입력 파라미터"""
    total_asset: float  # 총 자산 (USD)
    risk_ratio: float  # 최대 리스크 비율 (5~20%)
    direction: Literal["LONG", "SHORT"]  # 포지션 방향
    entry_price: float  # 진입가
    stop_loss: float  # 스탑 로스
    take_profits: List[float]  # 익절가 리스트 (1차, 2차, 3차...)
    margin_usage_ratio: float = 60.0  # 사용 가능 Margin 비율 (%) - 총 자산 대비 % (기본값 60%)


@dataclass
class TradingResults:
    """계산 결과"""
    # 1. 손절 정보
    stop_loss_pct: float  # 손절 폭 (%)
    stop_loss_price: float  # 손절가
    actual_loss_amount: float  # 실제 손실 금액
    
    # 2. 포지션 크기
    position_notional: float  # 포지션 크기 (Notional)
    position_quantity: float  # 포지션 수량
    
    # 3. 레버리지
    position_leverage: float  # 포지션 사용 레버리지
    effective_leverage: float  # 실질 레버리지
    
    # 4. 손익비 및 수익 (딕셔너리로 동적 저장)
    take_profit_results: Dict[int, Dict[str, float]]  # {차수: {rr_ratio, actual_rr, profit}}
    
    # 5. 구조적 문제
    structural_issue: str  # 구조적 문제 여부
    
    # 6. Margin
    required_margin: float  # 필요 Margin
    
    # 7. 종합 판정
    overall_judgment: str  # 종합 판정
    
    # 8. 실제 진입 포지션
    actual_entry_notional: float  # 실제 진입 Notional
    actual_entry_quantity: float  # 실제 진입 수량
    actual_entry_leverage: float  # 실제 진입 레버리지


def calculate_risk_amount(total_asset: float, risk_ratio: float) -> float:
    """리스크 금액 계산"""
    return total_asset * (risk_ratio / 100)


def calculate_stop_loss(
    direction: Literal["LONG", "SHORT"],
    entry_price: float,
    stop_loss: float
) -> Tuple[float, float]:
    """손절 정보 계산"""
    if direction == "LONG":
        stop_loss_pct = ((entry_price - stop_loss) / entry_price) * 100
        stop_loss_price = stop_loss
    else:  # SHORT
        stop_loss_pct = ((stop_loss - entry_price) / entry_price) * 100
        stop_loss_price = stop_loss
    
    return stop_loss_pct, stop_loss_price


def calculate_position_size(
    direction: Literal["LONG", "SHORT"],
    entry_price: float,
    stop_loss: float,
    risk_amount: float
) -> Tuple[float, float]:
    """포지션 사이즈 계산 (리스크 기반)"""
    # 손절 시 가격 차이
    if direction == "LONG":
        price_diff = entry_price - stop_loss
    else:  # SHORT
        price_diff = stop_loss - entry_price
    
    # 리스크 금액 = price_diff * quantity + (entry + sl) * quantity * TAKER_FEE_RATE
    # quantity = risk_amount / (price_diff + (entry + sl) * TAKER_FEE_RATE)
    fee_per_unit = (entry_price + stop_loss) * TAKER_FEE_RATE
    quantity = risk_amount / (price_diff + fee_per_unit)
    
    # Notional = 진입가 * 수량
    notional = entry_price * quantity
    
    return notional, quantity


def calculate_actual_loss(
    direction: Literal["LONG", "SHORT"],
    entry_price: float,
    stop_loss: float,
    notional: float,
    quantity: float
) -> float:
    """실제 손실 금액 계산 (수수료 포함)"""
    # 손절 시 가격 차이로 인한 손실
    if direction == "LONG":
        price_loss = (entry_price - stop_loss) * quantity
    else:  # SHORT
        price_loss = (stop_loss - entry_price) * quantity
    
    # 수수료 (진입 + 손절)
    entry_fee = notional * TAKER_FEE_RATE
    exit_fee = stop_loss * quantity * TAKER_FEE_RATE
    
    # 실제 손실 = 가격 손실 + 수수료
    actual_loss = price_loss + entry_fee + exit_fee
    
    return actual_loss


def calculate_leverage(
    position_notional: float,
    risk_amount: float,
    total_asset: float,
    margin_usage_ratio: float = 60.0
) -> Tuple[float, float, float]:
    """레버리지 계산"""
    # 최소 Margin = 총 자산 * (margin_usage_ratio / 100)
    # 예: margin_usage_ratio = 60.0이면 총 자산의 60%를 Margin으로 사용
    min_margin = total_asset * (margin_usage_ratio / 100.0)
    
    # 최적 레버리지 계산
    if position_notional / min_margin <= MAX_LEVERAGE:
        leverage = position_notional / min_margin
        if leverage < MIN_LEVERAGE:
            leverage = MIN_LEVERAGE
    else:
        leverage = MAX_LEVERAGE
    
    required_margin = position_notional / leverage
    
    # 실질 레버리지 = 총 자산 대비 Notional
    effective_leverage = position_notional / total_asset
    
    return leverage, effective_leverage, required_margin


def calculate_rr_and_profit(
    direction: Literal["LONG", "SHORT"],
    entry_price: float,
    stop_loss: float,
    take_profits: List[float],
    notional: float,
    quantity: float,
    stop_loss_pct: float
) -> Dict[int, Dict[str, float]]:
    """손익비 및 수익 계산 (동적 익절가 처리)"""
    # 실제 손실 (수수료 포함) - 모든 익절가에 공통
    entry_fee = notional * TAKER_FEE_RATE
    sl_exit_fee = stop_loss * quantity * TAKER_FEE_RATE
    
    if direction == "LONG":
        price_loss = (entry_price - stop_loss) * quantity
    else:  # SHORT
        price_loss = (stop_loss - entry_price) * quantity
    
    actual_loss_with_fee = price_loss + entry_fee + sl_exit_fee
    
    # 각 익절가별 계산
    results = {}
    
    for idx, take_profit in enumerate(take_profits, start=1):
        # 이익 퍼센트 계산
        if direction == "LONG":
            profit_pct = ((take_profit - entry_price) / entry_price) * 100
        else:  # SHORT
            profit_pct = ((entry_price - take_profit) / entry_price) * 100
        
        # 이론적 손익비
        rr_ratio = profit_pct / stop_loss_pct if stop_loss_pct > 0 else 0
        
        # 실제 수익 (수수료 차감)
        if direction == "LONG":
            gross_profit = (take_profit - entry_price) * quantity
        else:  # SHORT
            gross_profit = (entry_price - take_profit) * quantity
        
        tp_exit_fee = take_profit * quantity * TAKER_FEE_RATE
        net_profit = gross_profit - entry_fee - tp_exit_fee
        
        actual_rr = net_profit / actual_loss_with_fee if actual_loss_with_fee > 0 else 0
        
        results[idx] = {
            "rr_ratio": rr_ratio,
            "actual_rr": actual_rr,
            "profit": net_profit
        }
    
    return results


def check_structural_issues(
    direction: Literal["LONG", "SHORT"],
    entry_price: float,
    stop_loss: float,
    take_profits: List[float]
) -> str:
    """구조적 문제 확인 (동적 익절가 처리)"""
    issues = []
    
    if direction == "LONG":
        if stop_loss >= entry_price:
            issues.append("스탑로스가 진입가보다 높거나 같음")
        
        # 각 익절가 검증
        prev_tp = entry_price
        for idx, take_profit in enumerate(take_profits, start=1):
            if take_profit <= entry_price:
                issues.append(f"{idx}차 익절이 진입가보다 낮거나 같음")
            if take_profit <= prev_tp:
                issues.append(f"{idx}차 익절이 이전 익절가보다 낮거나 같음")
            prev_tp = take_profit
    else:  # SHORT
        if stop_loss <= entry_price:
            issues.append("스탑로스가 진입가보다 낮거나 같음")
        
        # 각 익절가 검증
        prev_tp = entry_price
        for idx, take_profit in enumerate(take_profits, start=1):
            if take_profit >= entry_price:
                issues.append(f"{idx}차 익절이 진입가보다 높거나 같음")
            if take_profit >= prev_tp:
                issues.append(f"{idx}차 익절이 이전 익절가보다 높거나 같음")
            prev_tp = take_profit
    
    if not issues:
        return "문제 없음"
    return " / ".join(issues)


def judge_overall(
    leverage: float,
    stop_loss_pct: float,
    structural_issue: str
) -> str:
    """종합 판정"""
    judgments = []
    
    if structural_issue != "문제 없음":
        judgments.append("SL 조정 필요")
    
    if leverage > MAX_LEVERAGE:
        judgments.append("사이즈 조정 필요")
    elif leverage < MIN_LEVERAGE and stop_loss_pct < 1.0:
        judgments.append("사이즈 조정 필요")
    
    if stop_loss_pct > 5.0:  # 손절 폭이 너무 큼
        judgments.append("SL 조정 필요")
    
    if not judgments:
        return "문제 없음"
    
    return " / ".join(judgments)


def calculate_trading_results(inputs: TradingInputs) -> TradingResults:
    """모든 계산 수행 (메인 함수)"""
    # 리스크 금액 계산
    risk_amount = calculate_risk_amount(inputs.total_asset, inputs.risk_ratio)
    
    # 1. 손절 정보 계산
    stop_loss_pct, stop_loss_price = calculate_stop_loss(
        inputs.direction,
        inputs.entry_price,
        inputs.stop_loss
    )
    
    # 2. 포지션 사이즈 계산 (리스크 기반)
    position_notional, position_quantity = calculate_position_size(
        inputs.direction,
        inputs.entry_price,
        inputs.stop_loss,
        risk_amount
    )
    
    # 실제 손실 금액 계산 (수수료 포함)
    actual_loss = calculate_actual_loss(
        inputs.direction,
        inputs.entry_price,
        inputs.stop_loss,
        position_notional,
        position_quantity
    )
    
    # 3. 레버리지 계산
    position_leverage, effective_leverage, required_margin = calculate_leverage(
        position_notional,
        risk_amount,
        inputs.total_asset,
        inputs.margin_usage_ratio
    )
    
    # 4. 손익비 및 수익 계산
    take_profit_results = calculate_rr_and_profit(
        inputs.direction,
        inputs.entry_price,
        inputs.stop_loss,
        inputs.take_profits,
        position_notional,
        position_quantity,
        stop_loss_pct
    )
    
    # 5. 구조적 문제 확인
    structural_issue = check_structural_issues(
        inputs.direction,
        inputs.entry_price,
        inputs.stop_loss,
        inputs.take_profits
    )
    
    # 6. 종합 판정
    overall_judgment = judge_overall(
        position_leverage,
        stop_loss_pct,
        structural_issue
    )
    
    # 7. 실제 진입 포지션 (계산된 값 그대로 사용)
    actual_entry_notional = position_notional
    actual_entry_quantity = position_quantity
    actual_entry_leverage = position_leverage
    
    return TradingResults(
        stop_loss_pct=stop_loss_pct,
        stop_loss_price=stop_loss_price,
        actual_loss_amount=actual_loss,
        position_notional=position_notional,
        position_quantity=position_quantity,
        position_leverage=position_leverage,
        effective_leverage=effective_leverage,
        take_profit_results=take_profit_results,
        structural_issue=structural_issue,
        required_margin=required_margin,
        overall_judgment=overall_judgment,
        actual_entry_notional=actual_entry_notional,
        actual_entry_quantity=actual_entry_quantity,
        actual_entry_leverage=actual_entry_leverage
    )
