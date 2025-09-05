(function(){
  const e = React.createElement;
  const { useState, useEffect, useRef } = React;

  const TEST_TYPES = [
    { key: 'vibration', label: 'Vibration' },
    { key: 'oil', label: 'Oil Analysis' },
    { key: 'thermal', label: 'Thermography' },
    { key: 'ultra', label: 'Ultrasound' }
  ];

  // Mocked KPI data by test type
  const MOCK = {
    vibration: { completed: 42, pending: 13, delayed: 3, trend: [12,18,22,30,34,36,42,40,38,41,42,42] },
    oil:       { completed: 28, pending: 9, delayed: 1, trend: [5,8,10,12,14,16,18,20,22,25,26,28] },
    thermal:   { completed: 16, pending: 4, delayed: 2, trend: [2,3,4,6,8,10,11,12,13,14,15,16] },
    ultra:     { completed: 51, pending: 22, delayed: 8, trend: [20,22,26,28,30,31,35,40,42,45,48,51] }
  };

  function KpiCard({ title, value, accent }){
    return e('div', { className: `rounded-xl shadow-lg p-5 flex flex-col gap-2 ${accent} text-white` },
      e('div', { className: 'text-sm font-semibold opacity-90' }, title),
      e('div', { className: 'text-3xl font-extrabold' }, String(value))
    );
  }

  function Tabs({types, active, onChange}){
    return e('div', { className: 'flex gap-3 flex-wrap' },
      types.map(t => e('button', {
        key: t.key,
        onClick: ()=>onChange(t.key),
        className: `px-4 py-2 rounded-lg font-semibold ${active===t.key? 'bg-white shadow text-slate-900' : 'bg-transparent text-slate-700 border border-transparent hover:bg-white/60'}`
      }, t.label))
    );
  }

  function TrendChart({data, label}){
    const canvasRef = useRef(null);
    const chartRef = useRef(null);
    useEffect(()=>{
      if (!canvasRef.current) return;
      const ctx = canvasRef.current.getContext('2d');
      if (chartRef.current) chartRef.current.destroy();
      chartRef.current = new Chart(ctx, {
        type: 'line',
        data: {
          labels: Array.from({length: data.length}, (_,i)=>`W-${i+1}`),
          datasets: [{ label: label||'Trend', data: data, borderColor: '#06b6d4', backgroundColor: 'rgba(6,182,212,0.12)', fill: true, tension: 0.3, pointRadius: 3 }]
        },
        options: { responsive: true, maintainAspectRatio: false, plugins:{legend:{display:false}} }
      });
      return ()=>{ try{ chartRef.current.destroy(); }catch(_){} };
    }, [data, label]);
    return e('div', { className: 'w-full h-64 bg-white rounded-xl p-3 shadow' }, e('canvas', { ref: canvasRef }));
  }

  function App(){
    const [active, setActive] = useState('vibration');
    const [kpi, setKpi] = useState(MOCK.vibration);

    useEffect(()=>{
      // Try fetch server KPI endpoint; fall back to MOCK
      const typemap = { vibration: 'vibration', oil: 'oil', thermal: 'thermal', ultra: 'ultra' };
      const q = typemap[active] || active;
      fetch(`/api/testing/kpis?type=${encodeURIComponent(q)}&weeks=12`).then(r => r.json()).then(d => {
        if (d && (typeof d.completed !== 'undefined')) {
          setKpi({ completed: d.completed || 0, pending: d.pending || 0, delayed: d.delayed || 0, trend: Array.isArray(d.trend) ? d.trend : [] });
        } else {
          setKpi(MOCK[active] || { completed:0, pending:0, delayed:0, trend:[] });
        }
      }).catch(() => {
        setKpi(MOCK[active] || { completed:0, pending:0, delayed:0, trend:[] });
      });
    }, [active]);

    return e('div', { className: 'max-w-6xl mx-auto' },
      e('header', { className: 'mb-6' }, e('h1', { className: 'text-3xl font-extrabold' }, 'Testing Records')),
      e('div', { className: 'mb-4' }, e(Tabs, { types: TEST_TYPES, active: active, onChange: setActive })),
      e('div', { className: 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6' },
        e(KpiCard, { title: '✅ Completed this week', value: kpi.completed, accent: 'bg-gradient-to-tr from-green-600 to-green-400' }),
        e(KpiCard, { title: '⏳ Pending this week', value: kpi.pending, accent: 'bg-gradient-to-tr from-blue-600 to-cyan-400' }),
        e(KpiCard, { title: '⚠️ Delayed (over 1 week)', value: kpi.delayed, accent: 'bg-gradient-to-tr from-amber-600 to-amber-400' }),
        e(KpiCard, { title: '📊 History / Trend', value: '', accent: 'bg-gradient-to-tr from-slate-700 to-slate-500' })
      ),
      e('section', null, e(TrendChart, { data: kpi.trend || [], label: `${TEST_TYPES.find(t=>t.key===active).label} — Last 12` }))
    );
  }

  // Mount
  document.addEventListener('DOMContentLoaded', function(){
    const root = document.getElementById('testing-records-root');
    if (!root) return;
    ReactDOM.createRoot(root).render(e(App));
  });
})();
