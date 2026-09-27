// Original, invented game art for the trailer: icons, mini gameplay scenes and full phone
// screens. Nothing here copies a real game; the genres are generic (match-3 board, merge board,
// runner, strategy map, card battler, racer, shooter, idle RPG).
const GAMES = (() => {
  let seed = 11;
  const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
  const pick = (xs) => xs[Math.floor(rnd() * xs.length)];
  let uid = 0;
  const id = (p) => `${p}${uid++}`;

  // ---------------------------------------------------------------- icons (viewBox 0 0 40 40)
  const icon = {
    coin: () => { const g = id('c'); return `<svg viewBox="0 0 40 40"><defs><radialGradient id="${g}" cx="35%" cy="30%"><stop offset="0" stop-color="#fff6b0"/><stop offset=".45" stop-color="#ffc928"/><stop offset="1" stop-color="#d98a00"/></radialGradient></defs><circle cx="20" cy="20" r="17" fill="#b86e00"/><circle cx="20" cy="18.5" r="16" fill="url(#${g})"/><circle cx="20" cy="18.5" r="11" fill="none" stroke="#d98a00" stroke-width="2.4"/><path d="M20 11.5l2.2 4.6 5 .6-3.7 3.4 1 5-4.5-2.5-4.5 2.5 1-5-3.7-3.4 5-.6z" fill="#fff3a8"/></svg>`; },
    gem: (a = '#ff5fa2', b = '#b3126a') => { const g = id('g'); return `<svg viewBox="0 0 40 40"><defs><linearGradient id="${g}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs><path d="M9 14l6-7h10l6 7-11 19z" fill="url(#${g})" stroke="#fff" stroke-opacity=".5" stroke-width="1.2"/><path d="M9 14h22M15 7l5 7 5-7M20 14v19" stroke="#fff" stroke-opacity=".55" stroke-width="1.2" fill="none"/><path d="M12 13l4-4" stroke="#fff" stroke-width="2" stroke-linecap="round"/></svg>`; },
    bolt: () => `<svg viewBox="0 0 40 40"><path d="M23 3L8 23h10l-3 14 17-21H21z" fill="#ffd83a" stroke="#c77f00" stroke-width="2" stroke-linejoin="round"/></svg>`,
    chest: () => { const g = id('ch'); return `<svg viewBox="0 0 40 40"><defs><linearGradient id="${g}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#c9793d"/><stop offset="1" stop-color="#7a3d17"/></linearGradient></defs><rect x="5" y="17" width="30" height="17" rx="3" fill="url(#${g})" stroke="#4a2208" stroke-width="1.6"/><path d="M5 18c0-8 5-12 15-12s15 4 15 12z" fill="#d98a4a" stroke="#4a2208" stroke-width="1.6"/><rect x="5" y="16" width="30" height="4" fill="#ffc928" stroke="#a86b00" stroke-width="1"/><rect x="17" y="15" width="6" height="9" rx="1.5" fill="#ffe16b" stroke="#a86b00" stroke-width="1.2"/><path d="M11 6l1 3M29 6l-1 3M20 2v4" stroke="#fff6b0" stroke-width="2" stroke-linecap="round"/></svg>`; },
    gift: () => `<svg viewBox="0 0 40 40"><rect x="7" y="16" width="26" height="18" rx="3" fill="#3fbf7f" stroke="#1d7a4c" stroke-width="1.6"/><rect x="5" y="11" width="30" height="7" rx="2" fill="#56d493" stroke="#1d7a4c" stroke-width="1.6"/><rect x="17.5" y="11" width="5" height="23" fill="#ffd83a"/><path d="M20 11c-3-6-9-6-9-2s6 2 9 2c3 0 9 2 9-2s-6-4-9 2z" fill="#ffd83a" stroke="#c77f00" stroke-width="1.2"/></svg>`,
    lock: () => `<svg viewBox="0 0 40 40"><path d="M13 18v-5a7 7 0 0 1 14 0v5" fill="none" stroke="#e8e2f5" stroke-width="3.5"/><rect x="9" y="17" width="22" height="17" rx="4" fill="#e8e2f5" stroke="#7a6aa0" stroke-width="1.5"/><circle cx="20" cy="25" r="2.6" fill="#7a6aa0"/></svg>`,
    star: (c = '#ffd83a') => `<svg viewBox="0 0 40 40"><path d="M20 4l4.9 10 11 1.3-8.1 7.6 2.2 10.9L20 28.4l-10 5.4 2.2-10.9L4.1 15.3l11-1.3z" fill="${c}" stroke="#c77f00" stroke-width="1.8" stroke-linejoin="round"/></svg>`,
    shield: (c = '#3f7fe0', m = '#fff') => `<svg viewBox="0 0 40 40"><path d="M20 3l14 5v10c0 9-6 15-14 19C12 33 6 27 6 18V8z" fill="${c}" stroke="#1b1b2e" stroke-opacity=".35" stroke-width="2"/><path d="M20 10l3 6 6 .8-4.4 4.2 1 6-5.6-3-5.6 3 1-6-4.4-4.2 6-.8z" fill="${m}"/></svg>`,
    cart: () => `<svg viewBox="0 0 40 40"><path d="M5 8h5l4 17h17l4-12H12" fill="none" stroke="#fff" stroke-width="3.5" stroke-linejoin="round" stroke-linecap="round"/><circle cx="16" cy="31" r="3" fill="#fff"/><circle cx="29" cy="31" r="3" fill="#fff"/></svg>`,
    calendar: () => `<svg viewBox="0 0 40 40"><rect x="6" y="9" width="28" height="25" rx="4" fill="#fff"/><rect x="6" y="9" width="28" height="8" rx="3" fill="#ffd4e6"/><path d="M13 5v7M27 5v7" stroke="#fff" stroke-width="3.5" stroke-linecap="round"/><path d="M20 19l2 4.2 4.5.5-3.4 3.1 1 4.5-4.1-2.3-4.1 2.3 1-4.5-3.4-3.1 4.5-.5z" fill="#e0467a"/></svg>`,
    plane: (c = '#ff6b3d') => `<svg viewBox="0 0 120 60"><path d="M6 32c10-9 42-12 78-10 12 .8 22 4 28 10-6 5-16 8-28 8.6C48 42.4 16 40 6 32z" fill="#f4f6ff" stroke="#23305a" stroke-width="2.5"/><path d="M40 28L60 4h12L62 28zM44 38l14 18h11l-7-18z" fill="${c}" stroke="#23305a" stroke-width="2.5" stroke-linejoin="round"/><path d="M8 32L2 16h9l12 12z" fill="${c}" stroke="#23305a" stroke-width="2.5" stroke-linejoin="round"/><path d="M86 25c6 0 12 2.5 16 6H88z" fill="#7fd6ff" stroke="#23305a" stroke-width="2"/><g fill="#7fd6ff">${[30, 42, 54, 66, 78].map((x) => `<rect x="${x}" y="28" width="6" height="5" rx="1.5"/>`).join('')}</g></svg>`,
    ad: () => `<svg viewBox="0 0 40 40"><rect x="4" y="9" width="32" height="22" rx="5" fill="#fff"/><path d="M17 14v12l10-6z" fill="#e0463d"/></svg>`,
    trophy: () => `<svg viewBox="0 0 40 40"><path d="M12 6h16v8a8 8 0 0 1-16 0z" fill="#ffc928" stroke="#a86b00" stroke-width="1.8"/><path d="M12 9H6c0 6 3 8 7 8M28 9h6c0 6-3 8-7 8" fill="none" stroke="#a86b00" stroke-width="2"/><rect x="17" y="21" width="6" height="7" fill="#e0a300"/><rect x="11" y="28" width="18" height="6" rx="2" fill="#7a3d17"/></svg>`,
  };
  const i = (name, size, ...args) => `<span class="gi" style="width:${size}px;height:${size}px">${icon[name](...args)}</span>`;

  // ---------------------------------------------------------------- mini gameplay scenes
  const PAL = ['#ff4d6d', '#ffb703', '#3ec46d', '#3a86ff', '#b15cff', '#ff7b2e'];
  const gemShape = (x, y, s, c) => {
    const k = Math.floor(rnd() * 5), h = s / 2, cx = x + h, cy = y + h;
    const shine = `<ellipse cx="${cx - s * .15}" cy="${cy - s * .18}" rx="${s * .14}" ry="${s * .09}" fill="#fff" opacity=".7"/>`;
    const shapes = [
      `<circle cx="${cx}" cy="${cy}" r="${h * .86}" fill="${c}"/>`,
      `<rect x="${x + s * .1}" y="${y + s * .1}" width="${s * .8}" height="${s * .8}" rx="${s * .18}" fill="${c}"/>`,
      `<path d="M${cx} ${y + s * .06}L${x + s * .94} ${cy}L${cx} ${y + s * .94}L${x + s * .06} ${cy}z" fill="${c}"/>`,
      `<path d="M${cx} ${y + s * .08}L${x + s * .92} ${y + s * .86}H${x + s * .08}z" fill="${c}"/>`,
      `<path d="M${x + s * .28} ${y + s * .1}H${x + s * .72}L${x + s * .94} ${cy}L${x + s * .72} ${y + s * .9}H${x + s * .28}L${x + s * .06} ${cy}z" fill="${c}"/>`,
    ];
    return `<g stroke="#000" stroke-opacity=".25" stroke-width="${s * .05}">${shapes[k]}</g>${shine}`;
  };
  const scenes = {
    match3(w, h) {
      const n = 7, s = Math.min(w, h * 1.4) / (n + 1.2), ox = (w - s * n) / 2, oy = (h - s * Math.min(n, Math.floor(h / s))) / 2;
      let cells = '';
      const rows = Math.floor((h - 4) / s);
      for (let r = 0; r < rows; r++) for (let c = 0; c < n; c++) {
        cells += `<rect x="${ox + c * s}" y="${oy + r * s}" width="${s}" height="${s}" fill="${(r + c) % 2 ? '#2b2152' : '#342864'}"/>`;
        cells += gemShape(ox + c * s + s * .08, oy + r * s + s * .08, s * .84, pick(PAL));
      }
      return `<rect width="${w}" height="${h}" fill="#1a1238"/>${cells}`;
    },
    merge(w, h) {
      const n = 5, s = Math.min(w / n, h / 4) * .92, ox = (w - s * n) / 2, oy = (h - s * 3.6) / 2;
      let out = `<rect width="${w}" height="${h}" fill="#bfe8a8"/>`;
      for (let r = 0; r < 4; r++) for (let c = 0; c < n; c++) {
        out += `<rect x="${ox + c * s + 2}" y="${oy + r * s * .9 + 2}" width="${s - 4}" height="${s * .9 - 4}" rx="${s * .18}" fill="#e9f7d9" stroke="#8ec77a" stroke-width="1.5"/>`;
        if (rnd() < .7) {
          const cx = ox + c * s + s / 2, cy = oy + r * s * .9 + s * .45;
          const t = Math.floor(rnd() * 3);
          out += t === 0 ? `<circle cx="${cx}" cy="${cy}" r="${s * .26}" fill="${pick(['#ff7aa8', '#ffb703', '#b15cff'])}"/><circle cx="${cx}" cy="${cy}" r="${s * .1}" fill="#fff4a8"/>`
            : t === 1 ? `<rect x="${cx - s * .24}" y="${cy - s * .2}" width="${s * .48}" height="${s * .4}" rx="${s * .06}" fill="#c9793d" stroke="#7a3d17" stroke-width="1.5"/>`
              : `<path d="M${cx} ${cy - s * .28}l${s * .1} ${s * .2} ${s * .2} ${s * .03}-${s * .15} ${s * .14} ${s * .04} ${s * .2}-${s * .19}-${s * .1}-${s * .19} ${s * .1} ${s * .04}-${s * .2}-${s * .15}-${s * .14} ${s * .2}-${s * .03}z" fill="#ffd83a"/>`;
          if (rnd() < .4) out += `<circle cx="${cx + s * .3}" cy="${cy - s * .28}" r="${s * .12}" fill="#3a86ff" stroke="#fff" stroke-width="1.5"/><text x="${cx + s * .3}" y="${cy - s * .23}" font-size="${s * .16}" text-anchor="middle" fill="#fff" font-family="Fredoka" font-weight="700">${1 + Math.floor(rnd() * 5)}</text>`;
        }
      }
      return out;
    },
    runner(w, h) {
      const sky = pick([['#6fc3ff', '#d9f1ff'], ['#ff9a6b', '#ffe1a8'], ['#7b6cff', '#ffb3e0']]);
      const g = id('rs');
      let out = `<defs><linearGradient id="${g}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${sky[0]}"/><stop offset="1" stop-color="${sky[1]}"/></linearGradient></defs><rect width="${w}" height="${h}" fill="url(#${g})"/>`;
      for (let k = 0; k < 3; k++) { const x = rnd() * w, y = rnd() * h * .4; out += `<g fill="#fff" opacity=".9"><ellipse cx="${x}" cy="${y + 8}" rx="${w * .12}" ry="${h * .06}"/><circle cx="${x - w * .04}" cy="${y + 4}" r="${h * .07}"/><circle cx="${x + w * .03}" cy="${y + 2}" r="${h * .09}"/></g>`; }
      for (let k = 0; k < 5; k++) { const x = k * w / 4 - 10, bw = w * .18, bh = h * (.25 + rnd() * .35); out += `<rect x="${x}" y="${h * .78 - bh}" width="${bw}" height="${bh}" fill="#5a6fb5" opacity=".55"/>`; }
      out += `<rect y="${h * .78}" width="${w}" height="${h * .22}" fill="#4cae4f"/><rect y="${h * .78}" width="${w}" height="${h * .04}" fill="#7ed957"/>`;
      for (let k = 0; k < 6; k++) out += `<circle cx="${w * .45 + k * w * .08}" cy="${h * .45 - Math.sin(k / 5 * Math.PI) * h * .15}" r="${h * .04}" fill="#ffc928" stroke="#b86e00" stroke-width="1"/>`;
      out += `<g transform="translate(${w * .2},${h * .56})"><rect x="-6" y="-18" width="16" height="22" rx="6" fill="#ff4d6d"/><circle cx="2" cy="-24" r="8" fill="#ffd9b8"/><rect x="-8" y="4" width="6" height="10" rx="3" fill="#23305a"/><rect x="4" y="4" width="6" height="10" rx="3" fill="#23305a"/></g>`;
      return out;
    },
    strategy(w, h) {
      let out = `<rect width="${w}" height="${h}" fill="#5c8f3a"/>`;
      const s = w / 7;
      for (let r = 0; r < Math.ceil(h / (s * .75)) + 1; r++) for (let c = 0; c < 8; c++) {
        const x = c * s + (r % 2) * s / 2 - s / 2, y = r * s * .75 - s / 2;
        const f = pick(['#6aa84f', '#77b255', '#5c8f3a', '#c2b280', '#4f86c6', '#6aa84f']);
        out += `<path d="M${x + s / 2} ${y}l${s / 2} ${s / 4}v${s / 2}l-${s / 2} ${s / 4}-${s / 2}-${s / 4}v-${s / 2}z" fill="${f}" stroke="#3b5e24" stroke-width="1"/>`;
        if (f === '#6aa84f' && rnd() < .5) out += `<path d="M${x + s / 2} ${y + s * .2}l${s * .18} ${s * .38}h-${s * .36}z" fill="#2f6b2f"/>`;
      }
      for (let k = 0; k < 3; k++) { const x = w * (.2 + rnd() * .6), y = h * (.2 + rnd() * .6), c = pick(['#e0463d', '#3a86ff', '#ffb703']); out += `<g><rect x="${x - 10}" y="${y - 8}" width="20" height="14" fill="#d9d2c3" stroke="#555" stroke-width="1"/><path d="M${x - 12} ${y - 8}h24l-12-10z" fill="${c}"/><rect x="${x - 3}" y="${y}" width="6" height="6" fill="#555"/><rect x="${x - 16}" y="${y + 9}" width="32" height="6" rx="3" fill="#000" opacity=".45"/><rect x="${x - 15}" y="${y + 10}" width="${22 * rnd() + 6}" height="4" rx="2" fill="${c}"/></g>`; }
      return out;
    },
    cards(w, h) {
      let out = `<rect width="${w}" height="${h}" fill="#2a1a3d"/><ellipse cx="${w / 2}" cy="${h * .45}" rx="${w * .45}" ry="${h * .3}" fill="#3d2659"/>`;
      const n = 5;
      for (let k = 0; k < n; k++) {
        const a = (k - (n - 1) / 2) * 11, cw = w * .2, ch = cw * 1.4, c = pick(PAL);
        out += `<g transform="translate(${w / 2},${h * 1.02}) rotate(${a}) translate(${-cw / 2},${-ch - h * .12})"><rect width="${cw}" height="${ch}" rx="6" fill="#f3e9d2" stroke="#c9a94f" stroke-width="2"/><rect x="4" y="4" width="${cw - 8}" height="${ch * .5}" rx="4" fill="${c}"/><circle cx="${cw / 2}" cy="${ch * .3}" r="${cw * .16}" fill="#fff" opacity=".6"/><circle cx="6" cy="6" r="6" fill="#3a86ff" stroke="#fff" stroke-width="1.5"/><rect x="6" y="${ch * .62}" width="${cw - 12}" height="3" fill="#c9a94f"/><rect x="6" y="${ch * .72}" width="${cw - 20}" height="3" fill="#c9a94f"/></g>`;
      }
      return out;
    },
    racer(w, h) {
      const g = id('rc');
      let out = `<defs><linearGradient id="${g}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffb36b"/><stop offset="1" stop-color="#ffe6c2"/></linearGradient></defs><rect width="${w}" height="${h * .45}" fill="url(#${g})"/><rect y="${h * .45}" width="${w}" height="${h * .55}" fill="#3a9d4a"/>`;
      out += `<path d="M${w * .46} ${h * .45}h${w * .08}L${w * .95} ${h}H${w * .05}z" fill="#555"/>`;
      for (let k = 0; k < 5; k++) { const t = k / 5, y = h * .45 + (h * .55) * t * t; out += `<rect x="${w / 2 - 1 - t * 3}" y="${y}" width="${2 + t * 6}" height="${3 + t * 10}" fill="#fff"/>`; }
      out += `<g transform="translate(${w * .5},${h * .82})"><rect x="-${w * .09}" y="-${h * .1}" width="${w * .18}" height="${h * .14}" rx="6" fill="${pick(['#e0463d', '#3a86ff', '#ffb703'])}" stroke="#222" stroke-width="1.5"/><rect x="-${w * .06}" y="-${h * .16}" width="${w * .12}" height="${h * .08}" rx="4" fill="#7fd6ff" stroke="#222" stroke-width="1.5"/></g>`;
      return out;
    },
    shooter(w, h) {
      let out = `<rect width="${w}" height="${h}" fill="#3d4a5c"/><path d="M0 0L${w * .3} ${h * .3}H${w * .7}L${w} 0z" fill="#56657a"/><path d="M0 ${h}L${w * .3} ${h * .7}H${w * .7}L${w} ${h}z" fill="#2c3644"/><rect x="${w * .3}" y="${h * .3}" width="${w * .4}" height="${h * .4}" fill="#6b7d93"/>`;
      out += `<rect x="${w * .42}" y="${h * .38}" width="${w * .08}" height="${h * .22}" rx="4" fill="#c0392b"/><circle cx="${w * .46}" cy="${h * .35}" r="${h * .05}" fill="#e8c39e"/>`;
      out += `<g stroke="#7dff9a" stroke-width="2"><path d="M${w / 2 - 12} ${h / 2}h8M${w / 2 + 4} ${h / 2}h8M${w / 2} ${h / 2 - 12}v8M${w / 2} ${h / 2 + 4}v8"/></g>`;
      out += `<path d="M${w * .62} ${h}l${w * .1}-${h * .3}h${w * .12}l${w * .06} ${h * .3}z" fill="#222"/><rect x="${w * .06}" y="${h * .86}" width="${w * .22}" height="${h * .06}" rx="2" fill="#000" opacity=".5"/><rect x="${w * .07}" y="${h * .87}" width="${w * .15}" height="${h * .04}" fill="#7dff9a"/>`;
      return out;
    },
    idle(w, h) {
      let out = `<rect width="${w}" height="${h}" fill="#2d1b4e"/><rect y="${h * .7}" width="${w}" height="${h * .3}" fill="#4a2f7a"/>`;
      out += `<g transform="translate(${w * .25},${h * .68})"><rect x="-10" y="-30" width="20" height="30" rx="6" fill="#3a86ff"/><circle cy="-38" r="10" fill="#ffd9b8"/><path d="M8 -26l22 -18" stroke="#e8e8ff" stroke-width="4" stroke-linecap="round"/></g>`;
      out += `<g transform="translate(${w * .7},${h * .68})"><ellipse cy="-22" rx="${w * .12}" ry="${h * .22}" fill="#3ec46d"/><circle cx="-8" cy="-30" r="5" fill="#fff"/><circle cx="8" cy="-30" r="5" fill="#fff"/><circle cx="-8" cy="-30" r="2" fill="#000"/><circle cx="8" cy="-30" r="2" fill="#000"/></g>`;
      out += `<rect x="${w * .56}" y="${h * .12}" width="${w * .3}" height="6" rx="3" fill="#000" opacity=".5"/><rect x="${w * .56}" y="${h * .12}" width="${w * .3 * rnd()}" height="6" rx="3" fill="#ff4d6d"/>`;
      out += `<text x="${w * .62}" y="${h * .3}" fill="#ffd83a" font-family="Lilita One" font-size="${h * .14}" stroke="#7a3d17" stroke-width="1">-${Math.floor(100 + rnd() * 900)}</text>`;
      return out;
    },
  };
  const scene = (kind, w, h) => `<svg viewBox="0 0 ${w} ${h}" width="100%" height="100%" preserveAspectRatio="xMidYMid slice">${scenes[kind](w, h)}</svg>`;
  const KINDS = Object.keys(scenes);
  const randomScene = (w, h) => scene(pick(KINDS), w, h);

  return { icon, i, scene, randomScene, KINDS };
})();
