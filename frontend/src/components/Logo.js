import React, { useState, useEffect } from 'react';

const generateBlip = () => {
  const angle = Math.random() * 2 * Math.PI;
  const r = 10 + Math.random() * 18; // between inner and outer ring
  return {
    cx: 32 + r * Math.cos(angle),
    cy: 32 + r * Math.sin(angle),
    r: 1.2 + Math.random() * 1.2,
    opacity: 0.4 + Math.random() * 0.4,
    id: Math.random(),
  };
};

const Logo = ({ className = "w-6 h-6" }) => {
  const [blips, setBlips] = useState([]);

  useEffect(() => {
    const interval = setInterval(() => {
      setBlips((prev) => {
        const next = prev.filter((b) => b.opacity > 0.05).map((b) => ({ ...b, opacity: b.opacity - 0.08 }));
        if (next.length < 4) {
          next.push(generateBlip());
        }
        if (Math.random() > 0.5) {
          next.push(generateBlip());
        }
        return next.slice(-6);
      });
    }, 600);
    return () => clearInterval(interval);
  }, []);

  return (
    <svg
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      {/* Outer radar ring */}
      <circle
        cx="32"
        cy="32"
        r="29"
        stroke="#0a0a0a"
        strokeWidth="2.5"
        strokeOpacity="0.7"
        strokeDasharray="5 3"
      />

      {/* Middle radar ring */}
      <circle
        cx="32"
        cy="32"
        r="21"
        stroke="#0a0a0a"
        strokeWidth="1.8"
        strokeOpacity="0.45"
      />

      {/* Inner radar ring */}
      <circle
        cx="32"
        cy="32"
        r="13"
        stroke="#0a0a0a"
        strokeWidth="1.4"
        strokeOpacity="0.3"
      />

      {/* Radar sweep group - animated rotation */}
      <g style={{ transformOrigin: '32px 32px', animation: 'radarSpin 3s linear infinite' }}>
        {/* Radar sweep line */}
        <line
          x1="32"
          y1="32"
          x2="32"
          y2="4"
          stroke="#0a0a0a"
          strokeWidth="2"
          strokeOpacity="0.6"
          strokeLinecap="round"
        />

        {/* Radar sweep arc (gives the "scanning" feel) */}
        <path
          d="M32 32 L32 4 A28 28 0 0 1 55 17 Z"
          fill="#0a0a0a"
          fillOpacity="0.12"
        />
      </g>

      {/* Keyframes for radar spin */}
      <style>{`
        @keyframes radarSpin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>

      {/* JS text - bold, centered */}
      <text
        x="32"
        y="39"
        textAnchor="middle"
        fontFamily="Inter, system-ui, -apple-system, sans-serif"
        fontWeight="800"
        fontSize="19"
        fill="#0a0a0a"
        letterSpacing="-0.5"
      >
        JS
      </text>

      {/* Small crosshair dots on rings */}
      <circle cx="32" cy="3" r="2" fill="#0a0a0a" fillOpacity="0.7" />
      <circle cx="61" cy="32" r="1.5" fill="#0a0a0a" fillOpacity="0.4" />
      <circle cx="32" cy="61" r="1.5" fill="#0a0a0a" fillOpacity="0.4" />
      <circle cx="3" cy="32" r="1.5" fill="#0a0a0a" fillOpacity="0.4" />

      {/* Animated blip dots - randomly appear and fade out */}
      {blips.map((b) => (
        <circle
          key={b.id}
          cx={b.cx}
          cy={b.cy}
          r={b.r}
          fill="#0a0a0a"
          fillOpacity={b.opacity}
          style={{ transition: 'fill-opacity 0.5s ease-out' }}
        />
      ))}
    </svg>
  );
};

export default Logo;
