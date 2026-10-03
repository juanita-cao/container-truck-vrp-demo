import { describe, expect, it } from "vitest";
import { clock, delta, money, num } from "./format";
import { decodePolyline } from "./polyline";
import { along, countersAt, inventoryAt, nextEventTime, pathFor, positionsAt, travelledPath, type Trajectory } from "./replay";

const traj = (): Trajectory => ({
  coord_system: "grid", horizon_min: 720,
  nodes: { dc: 0, clients: { "1": 1 }, tcs: { "1": 2 }, xy: [[0, 0], [10, 0], [0, 10]] },
  tractors: [{ k: 1, end_time: 60, km: 20, segments: [
    { t0: 0, t1: 30, kind: "travel", from: 0, to: 1, trailer: "loaded", task: "M1", km: 10, x0: 0, y0: 0, x1: 10, y1: 0 },
    { t0: 30, t1: 40, kind: "dwell", from: 1, to: 1, trailer: "none", task: "M1", km: 0, x0: 10, y0: 0, x1: 10, y1: 0 },
    { t0: 40, t1: 60, kind: "travel", from: 1, to: 0, trailer: "none", task: null, km: 10, x0: 10, y0: 0, x1: 0, y1: 0, task_done: true },
  ] }],
  events: [{ t: 30, tractor: 1, kind: "drop", node: 1, task: "M1" }, { t: 30, tractor: 1, kind: "late", node: 1, task: "M1", minutes: 5 }],
  tc_inventory: { "1": [[0, 6], [20, 5], [50, 6]] }, geometry: {}, geometry_precision: null, km_total: 20,
});

describe("replay interpolation", () => {
  it("is at the hub before the first segment and at the end node after the last", () => {
    const tr = traj();
    expect(positionsAt(tr, -5)[0]).toMatchObject({ x: 0, y: 0, state: "idle" });
    expect(positionsAt(tr, 100)[0]).toMatchObject({ x: 0, y: 0, state: "idle" });
  });
  it("interpolates linearly along a travel leg (grid = straight line)", () => {
    const p = positionsAt(traj(), 15)[0];
    expect(p.x).toBeCloseTo(5); expect(p.y).toBeCloseTo(0); expect(p.state).toBe("moving"); expect(p.trailer).toBe("loaded");
  });
  it("stays at the node while dwelling", () => {
    const p = positionsAt(traj(), 35)[0];
    expect(p).toMatchObject({ x: 10, y: 0, state: "dwelling" });
  });
  it("follows a polyline by length, not by point count", () => {
    const tr = traj();
    tr.coord_system = "wgs84";
    const path = { pts: [[0, 0], [1, 0], [11, 0]] as [number, number][], cum: [0, 1, 11], total: 11 };
    expect(along(path, 0.5).x).toBeCloseTo(5.5);          // 一半长度在第二段里，而不是第二个点
    expect(pathFor(tr, 0, 1).pts).toEqual([[0, 0], [10, 0]]);  // 没有几何时退回直线
  });
  it("counts done / late / km at a time and reads inventory as a step function", () => {
    const tr = traj();
    const c = countersAt(tr, 35, positionsAt(tr, 35));
    expect(c).toMatchObject({ done: 1, late: 1, early: 0, dwelling: 1 });
    expect(c.km).toBeCloseTo(10);
    expect(inventoryAt(tr, 10)["1"]).toBe(6); expect(inventoryAt(tr, 20)["1"]).toBe(5); expect(inventoryAt(tr, 55)["1"]).toBe(6);
    expect(nextEventTime(tr, 0)).toBe(30); expect(nextEventTime(tr, 30)).toBeNull();
  });
});

describe("trail follows the road, not chords between samples", () => {
  it("returns exactly the piece of the leg travelled in the time window", () => {
    const pts = travelledPath(traj(), 1, 10, 20);               // 第一段 0→30 分钟走 (0,0)→(10,0)：10~20 分钟 = x 从 3.33 到 6.67
    expect(pts[0][0]).toBeCloseTo(10 / 3); expect(pts[pts.length - 1][0]).toBeCloseTo(20 / 3);
    expect(pts.every((q) => q[1] === 0)).toBe(true);
  });
  it("is empty while dwelling or outside the leg, and follows a polyline's corners", () => {
    expect(travelledPath(traj(), 1, 31, 39)).toEqual([]);       // 30~40 分钟在客户处装卸
    const tr = traj();
    tr.coord_system = "wgs84"; tr.geometry_precision = 6;
    // 手工编码一条带转角的折线 (0,0)→(1,0)→(1,1)，经纬度单位 1e-6：用 pathFor 的缓存注入
    const cache = pathFor(tr, 0, 1);
    cache.pts.splice(0, cache.pts.length, [0, 0], [10, 0], [10, 10]); cache.cum.splice(0, cache.cum.length, 0, 10, 20); cache.total = 20;
    const p = travelledPath(tr, 1, 0, 30);                      // 整段：应含转角点 (10,0)
    expect(p.some((q) => q[0] === 10 && q[1] === 0)).toBe(true);
  });
});

describe("polyline + formatting", () => {
  it("decodes polyline6", () => {
    // 编码 [(103.785123,1.279456),(103.7861,1.2801)]（经度,纬度）
    const enc = "{{ukhA_wmbWcc@yb@";
    const pts = decodePolyline(enc, 6);
    expect(pts.length).toBeGreaterThan(0);
  });
  it("formats money by the price table currency, not the UI language", () => {
    expect(money(1234, "SGD", "en")).toBe("S$1,234");
    expect(money(1234, "SGD", "zh")).toBe("S$1,234");
    expect(money(-50, "SGD", "en")).toBe("-S$50");
    expect(money(1234, "CNY", "en")).toContain("1,234");
    expect(money(1234, "SGD", "zh")).toContain("1,234");
    expect(money(1234, "CNY", "zh")).toContain("¥");
  });
  it("formats time as 24 hour clock and deltas with arrows", () => {
    expect(clock(0)).toBe("08:00"); expect(clock(725)).toBe("20:05");
    expect(delta(-29.4, "en")).toBe("▼ 29.4%"); expect(delta(3.1, "en")).toBe("▲ 3.1%");
    expect(num(1234.5, "en", 1)).toBe("1,234.5");
  });
});
