import { useEffect, useRef } from "react";
import * as echarts from "echarts";

/** 极简 ECharts 封装：option 变化即 setOption（notMerge），卸载销毁，窗口缩放自适应。 */
export default function Chart({ option, height = 280 }: { option: echarts.EChartsOption | object; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const instRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const inst = echarts.init(el);
    instRef.current = inst;
    const ro = new ResizeObserver(() => inst.resize());
    ro.observe(el);
    return () => { ro.disconnect(); inst.dispose(); instRef.current = null; };
  }, []);

  useEffect(() => {
    const inst = instRef.current;
    if (inst && option) inst.setOption(wrapOption(option) as Parameters<typeof inst.setOption>[0], true);
  }, [option]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}

function wrapOption(opt: object): object {
  const o = opt as Record<string, any>;
  if (o.backgroundColor) return o;
  return {
    backgroundColor: "transparent",
    textStyle: { color: "#94a3b8" },
    grid: o.grid ?? { left: 46, right: 46, top: 42, bottom: 34 },
    ...o,
    tooltip: o.tooltip ? { confine: true, ...(typeof o.tooltip === "object" ? o.tooltip : {}) } : { confine: true },
  };
}
