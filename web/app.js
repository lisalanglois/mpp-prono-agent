const STORAGE_KEY = "cdm2026_pronos";

let matches = [];

async function loadMatches() {
  const res = await fetch("matches.json");
  matches = await res.json();
  render();
}

function getSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function save(id, home, away) {
  const data = getSaved();
  data[id] = { home, away };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  updateProgress();
}

function render() {
  const saved = getSaved();
  const byDate = {};
  for (const m of matches) {
    (byDate[m.date] ||= []).push(m);
  }

  const main = document.getElementById("matches");
  main.innerHTML = "";

  const dates = Object.keys(byDate).sort((a, b) => {
    const [da, ma] = a.split("/").map(Number);
    const [db, mb] = b.split("/").map(Number);
    return ma - mb || da - db;
  });

  for (const date of dates) {
    const group = document.createElement("div");
    group.className = "day-group";
    const label = formatDate(date);
    group.innerHTML = `<div class="day-title">${label}</div>`;

    for (const m of byDate[date]) {
      const s = saved[m.id] || {};
      const sh = s.home ?? "";
      const sa = s.away ?? "";
      const card = document.createElement("div");
      card.className = "match-card" + (sh !== "" && sa !== "" ? " filled" : "");
      card.dataset.id = m.id;

      const probs = m.probs?.home
        ? `1 ${m.probs.home} · N ${m.probs.draw} · 2 ${m.probs.away}`
        : "";

      card.innerHTML = `
        <div class="team home">${m.home}</div>
        <div class="score-inputs">
          <input type="number" min="0" max="9" class="score-home" value="${sh}" placeholder="-" />
          <span>:</span>
          <input type="number" min="0" max="9" class="score-away" value="${sa}" placeholder="-" />
        </div>
        <div class="team away">${m.away}</div>
        <div class="match-meta">
          <span>${probs}</span>
          <span class="suggestion" title="Cliquer pour appliquer">IA → ${m.suggested}</span>
        </div>
      `;

      const homeIn = card.querySelector(".score-home");
      const awayIn = card.querySelector(".score-away");

      const onChange = () => {
        save(m.id, homeIn.value, awayIn.value);
        card.classList.toggle("filled", homeIn.value !== "" && awayIn.value !== "");
      };
      homeIn.addEventListener("input", onChange);
      awayIn.addEventListener("input", onChange);

      card.querySelector(".suggestion").addEventListener("click", () => {
        const [h, a] = m.suggested.split("-");
        homeIn.value = h;
        awayIn.value = a;
        onChange();
      });

      group.appendChild(card);
    }
    main.appendChild(group);
  }
  updateProgress();
}

function formatDate(d) {
  const [day, month] = d.split("/");
  const names = ["", "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre"];
  return `${parseInt(day)} ${names[parseInt(month)]} 2026`;
}

function updateProgress() {
  const saved = getSaved();
  const filled = matches.filter((m) => {
    const s = saved[m.id];
    return s && s.home !== "" && s.away !== "";
  }).length;
  document.getElementById("progress").textContent =
    `${filled} / ${matches.length} remplis`;
}

document.getElementById("btn-fill").addEventListener("click", () => {
  for (const m of matches) {
    const [h, a] = m.suggested.split("-");
    save(m.id, h, a);
  }
  render();
});

document.getElementById("btn-export").addEventListener("click", () => {
  const saved = getSaved();
  const lines = matches
    .filter((m) => saved[m.id]?.home !== "" && saved[m.id]?.away !== "")
    .map((m) => {
      const s = saved[m.id];
      return `${m.date} | ${m.home} ${s.home}-${s.away} ${m.away}`;
    });
  const text = lines.join("\n") || "Aucun prono rempli.";
  navigator.clipboard.writeText(text).then(() => {
    alert(`${lines.length} pronos copiés dans le presse-papier !`);
  });
});

loadMatches();
