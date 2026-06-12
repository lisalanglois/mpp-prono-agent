function mppCard(home, away, h, a, opts = {}) {
  const { date = "", subtitle = "", change = false, oldH, oldA } = opts;
  const cls = change ? "match-card change-needed" : "match-card filled";
  let oldHtml = "";
  if (oldH != null && oldA != null && (oldH !== h || oldA !== a)) {
    oldHtml = `<div class="old-score">Ancien : <span class="score-box old">${oldH}</span> : <span class="score-box old">${oldA}</span></div>`;
  }
  return `
    <div class="${cls}">
      ${date ? `<div class="card-date">${date}</div>` : ""}
      <div class="team home">${home}</div>
      <div class="score-inputs">
        ${oldHtml}
        <span class="score-box">${h}</span>
        <span>:</span>
        <span class="score-box">${a}</span>
      </div>
      <div class="team away">${away}</div>
      ${subtitle ? `<div class="card-sub">${subtitle}</div>` : ""}
    </div>`;
}

async function load() {
  const res = await fetch("tracker.json?" + Date.now());
  if (!res.ok) throw new Error("tracker.json introuvable");
  return res.json();
}

function render(data) {
  const s = data.stats;
  const cfgUser = "Lisa";
  const app = document.getElementById("app");
  document.getElementById("updated").textContent = data.updated_at
    ? `Mis à jour : ${new Date(data.updated_at).toLocaleString("fr-FR")}`
    : "";

  let html = `
    <div class="explain-box">
      <strong>Mon Petit Prono</strong> — jeu entre amis sur mpp.football.<br>
      <strong>${cfgUser}</strong> = ta grille · <strong>Klement</strong> = économiste (modèle macro, Pays-Bas champion).<br>
      On compare surtout <strong>1/N/2</strong> (qui gagne ou nul) — le score exact est un bonus.
    </div>
    <div class="scoreboard">
      <div class="score-card ${data.leader_1n2 === "toi" ? "leader" : ""}">
        <div class="label">${cfgUser}</div>
        <div class="value">${s.user_1n2_pct}%</div>
        <div class="label">${s.user_1n2}/${s.played} direction · ${s.user_exact} exact</div>
      </div>
      <div class="score-card ${data.leader_1n2 === "klement" ? "leader" : ""}">
        <div class="label">Klement</div>
        <div class="value">${s.klement_1n2_pct}%</div>
        <div class="label">${s.klement_1n2}/${s.played} direction</div>
      </div>
      <div class="score-card ${data.leader_1n2 === "modèle" ? "leader" : ""}">
        <div class="label">Modèle IA</div>
        <div class="value">${s.model_1n2_pct}%</div>
        <div class="label">${s.model_1n2}/${s.played}</div>
      </div>
    </div>
    <p class="winner-picks">
      Vainqueur MPP : <strong>${data.mpp_winner_pick}</strong> ·
      Klement avait : <strong>${data.klement_winner_pick || "—"}</strong>
    </p>
  `;

  const recent = data.recent_results?.length ? data.recent_results : data.matches?.slice(-1) || [];
  if (recent.length) {
    html += `<h2 class="section-title">🏁 Dernier(s) résultat(s)</h2>`;
    for (const r of recent) {
      html += mppCard(r.home, r.away, r.actual_home || "?", r.actual_away || "?", {
        subtitle: "Résultat réel",
      });
      html += `
        <div class="verdict-box">
          <div><strong>${cfgUser}</strong> : ${r.user_score || "—"} (${r.user_direction || "—"})
            ${r.user_1n2 ? "✅" : r.user_1n2 === false ? "❌" : "—"}</div>
          <div><strong>Klement</strong> : ${r.klement_direction || "—"}
            ${r.klement_1n2 ? "✅" : r.klement_1n2 === false ? "❌" : "—"}</div>
          <div class="verdict-main">${r.verdict_short || ""}</div>
        </div>`;
    }
  }

  if (data.upcoming_updates?.length) {
    html += `<h2 class="section-title">📋 À mettre sur mpp.football</h2>`;
    html += `<p class="hint">Recopie ces scores dans l'app (même format que les cases MPP) :</p>`;
    for (const u of data.upcoming_updates) {
      html += mppCard(u.home, u.away, u.suggested_home, u.suggested_away, {
        date: `${u.date} — avant match`,
        subtitle: u.mpp_action || u.reason,
        change: u.change,
        oldH: u.change ? u.current_home : null,
        oldA: u.change ? u.current_away : null,
      });
    }
  }

  if (data.alerts?.length) {
    html += `<h2 class="section-title">🔔 Points d'attention</h2>`;
    for (const a of data.alerts) {
      html += `<div class="alert-box ${a.level}"><strong>${a.message}</strong><br>${a.action}</div>`;
    }
  }

  if (!data.matches?.length && !data.upcoming_updates?.length) {
    html += `<p class="hint">Aucun match terminé pour l'instant — les emails partiront après chaque résultat.</p>`;
  }

  html += `<p class="hint" style="margin-top:1.5rem;text-align:center;">
    <a href="https://mpp.football" style="color:#1d9bf0;">Ouvrir mpp.football</a> ·
    <a href="index.html" style="color:#1d9bf0;">Grille complète</a>
  </p>`;

  app.innerHTML = html;
}

load().then(render).catch((e) => {
  document.getElementById("app").innerHTML =
    `<p style="color:#f87171;">Erreur : ${e.message}</p>`;
});
