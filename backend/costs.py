# -*- coding: utf-8 -*-
"""L1 财务指标：由 L2 运营驱动量 × 单价表折算。

单价表属于虚构演示公司，全部为虚构值，每一项都带 source 标注。
所有金额由本模块计算，前端与各方法都不得自行折算。
"""
from dataclasses import dataclass, field, asdict
from typing import Dict


@dataclass
class PriceTable:
    fuel_l_per_100km: float = 20.0       # 虚构
    fuel_price_per_l: float = 7.0        # 虚构
    driver_per_hour: float = 60.0        # 虚构
    tractor_fixed_per_day: float = 600.0  # 虚构：每辆**拥有**的牵引车（沉没成本，不因少用几辆而下降；配置扫描改变车队规模时才起作用）
    trailer_fixed_per_day: float = 100.0  # 虚构：挂车总量（配置扫描用；方法对比时为常量）
    outsource_per_task: float = 800.0    # 虚构：未完成/外包任务；必须高于自己服务一个任务的边际成本，否则优化器会靠"外包"让总成本变低
    penalty_per_minute: float = 2.0      # 虚构：早到/迟到折算（设 0 则惩罚只在 L3 展示）
    sources: Dict[str, str] = field(default_factory=lambda: {
        "fuel_l_per_100km": "fictional", "fuel_price_per_l": "fictional",
        "driver_per_hour": "fictional", "tractor_fixed_per_day": "fictional", "trailer_fixed_per_day": "fictional",
        "outsource_per_task": "fictional", "penalty_per_minute": "fictional",
    })
    version: str = "v1"
    currency: str = "CNY"                # 币种属于单价表，不随界面语言变（待用户确认新加坡演示是否改用 SGD）

    def to_dict(self):
        return asdict(self)


def default_price_table(dataset: str = "demo_sg") -> PriceTable:
    """新加坡演示公司的默认单价表：新加坡元（SGD，虚构价格）。"""
    if dataset == "demo_sg":
        return PriceTable(
            fuel_l_per_100km=28.0, fuel_price_per_l=2.30,        # 重型牵引车带挂车的油耗；新加坡柴油零售价量级
            driver_per_hour=16.0, tractor_fixed_per_day=130.0, trailer_fixed_per_day=25.0,
            outsource_per_task=150.0,                            # 必须高于自己服务一个任务的成本（约 S$80），否则优化器会靠外包"省钱"
            penalty_per_minute=0.40, version="v1", currency="SGD",
            sources={"fuel_l_per_100km": "fictional", "fuel_price_per_l": "fictional", "driver_per_hour": "fictional",
                     "tractor_fixed_per_day": "fictional", "trailer_fixed_per_day": "fictional",
                     "outsource_per_task": "fictional", "penalty_per_minute": "fictional"})
    return PriceTable()


def cost_breakdown(km: float, driver_minutes: float, tractors_owned: int, tractors_used: int, trailers_total: int,
                   penalty_minutes: float, unfinished: int, price: PriceTable) -> dict:
    """L2 驱动量 → L1 成本。driver_minutes：各使用牵引车从 08:00 到返回 DC 的分钟数之和（假设司机全程计薪）。"""
    fuel = km * price.fuel_l_per_100km / 100.0 * price.fuel_price_per_l
    driver = driver_minutes / 60.0 * price.driver_per_hour
    tractor = tractors_owned * price.tractor_fixed_per_day
    trailer = trailers_total * price.trailer_fixed_per_day
    outsource = unfinished * price.outsource_per_task
    penalty = penalty_minutes * price.penalty_per_minute
    total = fuel + driver + tractor + trailer + outsource + penalty
    return {"fuel": fuel, "driver": driver, "tractor_fixed": tractor, "trailer_fixed": trailer,
            "outsource": outsource, "penalty": penalty, "total": total,
            "drivers": {"km": km, "driver_hours": driver_minutes / 60.0, "tractors_owned": tractors_owned, "tractors_used": tractors_used,
                        "trailers_total": trailers_total, "penalty_minutes": penalty_minutes, "unfinished": unfinished}}
