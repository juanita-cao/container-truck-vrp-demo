import { describe, expect, it } from "vitest";
import { en } from "./en";
import { zh } from "./zh";
import { createI18n, detectLanguage } from "./index";

type Tree = { [k: string]: string | Tree };
function flatten(o: Tree, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(o)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out[key] = v;
    else Object.assign(out, flatten(v, key));
  }
  return out;
}
const placeholders = (s: string) => [...s.matchAll(/\{\{(\w+)\}\}/g)].map((m) => m[1]).sort().join(",");

describe("i18n resources", () => {
  const e = flatten(en as unknown as Tree);
  const z = flatten(zh as unknown as Tree);

  it("English and Chinese have exactly the same keys", () => {
    expect(Object.keys(z).sort()).toEqual(Object.keys(e).sort());
  });
  it("no empty strings", () => {
    for (const [k, v] of Object.entries(e)) expect(v.trim(), `en ${k}`).not.toBe("");
    for (const [k, v] of Object.entries(z)) expect(v.trim(), `zh ${k}`).not.toBe("");
  });
  it("placeholders match between languages", () => {
    for (const k of Object.keys(e)) expect(placeholders(z[k]), k).toBe(placeholders(e[k]));
  });
  it("switching language changes the text", async () => {
    const i = await createI18n("en");
    expect(i.t("nav.week")).toBe("Week overview");
    await i.changeLanguage("zh");
    expect(i.t("nav.week")).toBe("一周总览");
    expect(i.t("compare.spread", { n: 3 })).toBe("± 来自 3 次运行");
  });
  it("detects language: url > stored > browser", () => {
    expect(detectLanguage("?lang=zh", "en", "en-US")).toBe("zh");
    expect(detectLanguage("", "zh", "en-US")).toBe("zh");
    expect(detectLanguage("", null, "zh-CN")).toBe("zh");
    expect(detectLanguage("", null, "fr-FR")).toBe("en");
  });
});
