import React, { useEffect, useState } from 'react';
import { fetchGridForecast } from '../api';
import { ResponsiveContainer, ComposedChart, Line, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from 'recharts';

export default function GridTwin() {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [region, setRegion] = useState('WR');

  useEffect(() => {
    setLoading(true);
    fetchGridForecast(region)
      .then((res) => {
        // Map data to display format
        const formatted = res.forecast.map((d: any) => {
          const date = new Date(d.target_ts);
          return {
            time: date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            date_raw: date,
            ci_p50: d.ci_p50,
            ci_p90: d.ci_p90,
            ci_p10: d.ci_p10,
            solar: d.share_solar * 100,
            wind: d.share_wind * 100,
            demand: d.demand_mw,
          };
        });
        setData(formatted);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, [region]);

  return (
    <div className="space-y-6 h-full flex flex-col">
      <header className="flex justify-between items-end">
        <div>
          <h2 className="text-3xl font-bold">Grid Digital Twin</h2>
          <p className="text-muted-foreground mt-2">
            Forecasted Carbon Intensity (CI) and renewable generation for Indian Grid Regions.
          </p>
        </div>
        <select 
          value={region}
          onChange={(e) => setRegion(e.target.value)}
          className="bg-input border border-border text-foreground rounded-md px-4 py-2"
        >
          <option value="WR">Western Region (WR)</option>
          <option value="NR">Northern Region (NR)</option>
          <option value="SR">Southern Region (SR)</option>
          <option value="ER">Eastern Region (ER)</option>
        </select>
      </header>

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="animate-pulse text-muted-foreground">Loading physics engine...</p>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl p-6 shadow-sm flex-1 min-h-[400px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
              <XAxis dataKey="time" stroke="var(--muted-foreground)" tick={{fontSize: 12}} minTickGap={30} />
              <YAxis yAxisId="left" stroke="var(--muted-foreground)" label={{ value: 'CI (gCO₂/kWh)', angle: -90, position: 'insideLeft', fill: 'var(--muted-foreground)' }} />
              <YAxis yAxisId="right" orientation="right" stroke="var(--muted-foreground)" label={{ value: 'Generation Share (%)', angle: 90, position: 'insideRight', fill: 'var(--muted-foreground)' }} />
              <Tooltip 
                contentStyle={{ backgroundColor: 'var(--card)', borderColor: 'var(--border)' }}
                labelStyle={{ color: 'var(--foreground)' }}
              />
              <Legend />
              
              {/* Renewable Generation Bars */}
              <Bar yAxisId="right" dataKey="solar" stackId="a" fill="var(--chart-3)" name="Solar %" />
              <Bar yAxisId="right" dataKey="wind" stackId="a" fill="var(--chart-2)" name="Wind %" />
              
              {/* Carbon Intensity Line */}
              <Line yAxisId="left" type="monotone" dataKey="ci_p50" stroke="var(--chart-1)" strokeWidth={3} dot={false} name="Expected CI (p50)" />
              {/* Uncertainty bound */}
              <Line yAxisId="left" type="monotone" dataKey="ci_p90" stroke="var(--destructive)" strokeWidth={1} strokeDasharray="5 5" dot={false} name="Worst-case CI (p90)" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
