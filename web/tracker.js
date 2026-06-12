const OUTCOME = { home: "1", draw: "N", away: "2" };

async function load() {
  const res = await fetch("tracker.json?" + Date.now());
  if (!res.ok) throw new Error("tracker.json introuvable");
  return res.json();
}

function badge(ok) {
  if (ok === true) return '<span class="badge ok">✓</span>';
  if (ok === false) return '<span class="badge ko">✗</span>';
  return '<span class="badge na">—</span>';
}

function render(data) {
  const s = data.stats;
  const leader = data.leader_1n2;
  const app = document.getElementById("app");
  document.getElementById("updated").textContent = data.updated_at
    ? `Mis à jour : ${new Date(data.updated_at).toLocaleString("fr-FR")}`
    : "";

  let html = `
    <div class="scoreboard">
      <div class="score-card ${leader === "toi" ? "leader" : ""}">
        <div class="label">Toi — 1/N/2</div>
        <div class="value">${s.user_1n2_pct}%</div>
        <div class="label">${s.user_1n2}/${s.played} · exact ${s.user_exact}</div>
      </div>
      <div class="score-card ${leader === "modèle" ? "leader" : ""}">
        <div class="label">Modèle</div>
        <div class="value">${s.model_1n2_pct}%</div>
        <div class="label">${s.model_1n2}/${s.played}</div>
      </div>
      <div class="score-card ${leader === "klement" ? "leader" : ""}">
        <div class="label">Klement</div>
        <div class="value">${s.klement_1n2_pct}%</div>
        <div class="label">${s.klement_1n2}/${s.played}</div>
      </div>
    </div>
    <p class="winner-picks">
      Vainqueur MPP : <strong>${data.mpp_winner_pick}</strong> ·
      Klement : <strong>${data.klement_winner_pick || "—"}</strong>
    </p>
  `;

  if (data.upcoming_updates?.length) {
    html += "<h2 style='margin:1.5rem 0 0.75rem;font-size:1rem;'>📋 À revoir avant match</h2>";
    for (const u of data.upcoming_updates) {
      const ch = u.change ? " ← changement suggéré" : "";
      html += `
        <div class="alert-box info">
          <strong>${u.date}</strong> — ${u.match}<br>
          Actuel <strong>${u.current_score}</strong> → Suggéré <strong>${u.suggested_score}</strong>${ch}
          <div style="color:#8b98a5;font-size:0.85rem;margin-top:0.25rem;">${u.reason}</div>
        </div>`;
    }
  }

  if (data.alerts?.length) {
    html += "<h2 style='margin:1.5rem 0 0.75rem;font-size:1rem;'>🔔 Alertes</h2>";
    for (const a of data.alerts) {
      html += `
        <div class="alert-box ${a.level}">
          <strong>${a.match}</strong> — ${a.message}
          <div style="color:#8b98a5;font-size:0.85rem;margin-top:0.25rem;">→ ${a.action}</div>
        </div>`;
    }
  }

  if (data.matches?.length) {
    html += "<h2 style='margin:1.5rem 0 0.75rem;font-size:1rem;'>Matchs joués</h2>";
    html += '<div style="background:#192734;border:1px solid #2f3b47;border-radius:12px;padding:0 1rem;">';
    for (const m of data.matches) {
      html += `
        <div class="result-row">
          <div>
            <strong>${m.key}</strong>
            <div style="color:#8b98a5;font-size:0.8rem;">
              Réel ${m.actual_score}
              · Toi ${m.user_score || "—"} (${m.user_outcome ? OUTCOME[m.user_outcome] : "?"})
            </div>
          </div>
          <div title="Toi">${badge(m.user_1n2)}</div>
          <div title="Klement">${badge(m.klement_1n2)}</div>
        </div>`;
    }
    html += "</div>";
    html += '<p style="color:#8b98a5;font-size:0.75rem;margin-top:0.5rem;">Col. droite : toi · Klement</p>';
  } else {
    html += "<p style='color:#8b98a5;margin-top:1rem;'>Aucun match terminé pour l'instant.</p>";
  }

  app.innerHTML = html;
}

load().then(render).catch((e) => {
  document.getElementById("app").innerHTML =
    `<p style="color:#f87171;">Erreur : ${e.message}. Lance <code>python scripts/live_tracker.py</code> localement.</p>`;
});
