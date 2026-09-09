/* ═══════════════════════════════════════════
   LitScan 项目全景 · script.js
   导航高亮 / 进度条 / 目录树 / API 过滤 / 数字动画 / 主题切换
   ═══════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", function () {

  /* ── 1. 主题切换（默认跟随系统，可手动覆盖并记忆） ── */
  const themeToggle = document.getElementById("themeToggle");
  const stored = localStorage.getItem("litscan-theme");
  if (stored) {
    document.documentElement.setAttribute("data-theme", stored);
  } else if (window.matchMedia("(prefers-color-scheme: dark)").matches) {
    document.documentElement.setAttribute("data-theme", "dark");
  }
  themeToggle.addEventListener("click", function () {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("litscan-theme", next);
  });

  /* ── 2. 移动端汉堡菜单 ── */
  const navToggle = document.getElementById("navToggle");
  const navLinks = document.getElementById("navLinks");
  navToggle.addEventListener("click", function () {
    navToggle.classList.toggle("open");
    navLinks.classList.toggle("open");
  });
  navLinks.querySelectorAll("a").forEach(function (a) {
    a.addEventListener("click", function () {
      navToggle.classList.remove("open");
      navLinks.classList.remove("open");
    });
  });

  /* ── 3. 滚动进度条 + 返回顶部 ── */
  const progress = document.getElementById("scrollProgress");
  const backTop = document.getElementById("backTop");
  function onScroll() {
    const h = document.documentElement;
    const total = h.scrollHeight - h.clientHeight;
    const pct = total > 0 ? (h.scrollTop / total) * 100 : 0;
    progress.style.width = pct + "%";
    backTop.classList.toggle("show", h.scrollTop > window.innerHeight * 0.8);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
  backTop.addEventListener("click", function () {
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  /* ── 4. 导航 / 侧边栏滚动高亮 ── */
  const sections = Array.from(document.querySelectorAll(".section"));
  const navAnchors = Array.from(document.querySelectorAll(".nav-links a, .sidebar a"));
  const observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      const id = "#" + entry.target.id;
      navAnchors.forEach(function (a) {
        a.classList.toggle("active", a.getAttribute("href") === id);
      });
    });
  }, { rootMargin: "-30% 0px -65% 0px" });
  sections.forEach(function (s) { observer.observe(s); });

  /* ── 5. 目录树折叠 ── */
  document.querySelectorAll("[data-toggle]").forEach(function (toggle) {
    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      toggle.classList.toggle("open");
      const children = toggle.parentElement.nextElementSibling;
      if (children && children.classList.contains("tree-children")) {
        children.classList.toggle("open");
      }
    });
  });
  // 根节点默认展开
  const rootChildren = document.querySelector(".tree-children");
  if (rootChildren) rootChildren.classList.add("open");

  /* ── 6. API 方法过滤 ── */
  const apiTabs = Array.from(document.querySelectorAll(".api-tab"));
  const apiRows = Array.from(document.querySelectorAll("#apiTable tbody tr"));
  apiTabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      apiTabs.forEach(function (t) { t.classList.remove("active"); });
      tab.classList.add("active");
      const f = tab.dataset.filter;
      apiRows.forEach(function (row) {
        const show = f === "all" || row.dataset.method === f;
        row.classList.toggle("hidden-row", !show);
      });
    });
  });

  /* ── 7. 代码块复制 ── */
  document.querySelectorAll("[data-copy]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const block = btn.closest(".code-card").querySelector("code");
      if (!block) return;
      // 去掉行号 span
      const text = Array.from(block.childNodes)
        .filter(function (n) { return !(n.classList && n.classList.contains("ln")); })
        .map(function (n) { return n.textContent; })
        .join("");
      const done = function () {
        btn.textContent = "已复制";
        btn.classList.add("copied");
        setTimeout(function () {
          btn.textContent = "复制";
          btn.classList.remove("copied");
        }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done).catch(function () { fallbackCopy(text, done); });
      } else {
        fallbackCopy(text, done);
      }
    });
  });
  function fallbackCopy(text, cb) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); cb(); } catch (e) { /* noop */ }
    document.body.removeChild(ta);
  }

  /* ── 8. 数字计数动画 ── */
  const counters = Array.from(document.querySelectorAll("[data-count]"));
  if (counters.length) {
    const counterObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        const el = entry.target;
        const target = parseInt(el.dataset.count, 10) || 0;
        const suffix = el.dataset.suffix || "";
        const duration = 1100;
        const start = performance.now();
        function tick(now) {
          const p = Math.min((now - start) / duration, 1);
          const eased = 1 - Math.pow(1 - p, 3);
          el.textContent = Math.round(target * eased) + (p === 1 ? suffix : "");
          if (p < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
        counterObserver.unobserve(el);
      });
    }, { threshold: 0.4 });
    counters.forEach(function (c) { counterObserver.observe(c); });
  }

  /* ── 9. 章节进入动画 ── */
  const revealTargets = Array.from(document.querySelectorAll(".card, .section-title, .section-desc"));
  revealTargets.forEach(function (el) { el.classList.add("reveal"); });
  const revealObserver = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        revealObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.08 });
  revealTargets.forEach(function (el) { revealObserver.observe(el); });

  /* ── 10. 架构图 tooltip（SVG 内联） ── */
  const svg = document.querySelector(".arch-svg");
  const tip = document.getElementById("svgTooltip");
  if (svg && tip) {
    const tipRect = tip.querySelector("rect");
    const tipText = tip.querySelector("text");
    svg.querySelectorAll("[data-tip]").forEach(function (node) {
      node.addEventListener("mousemove", function (e) {
        const msg = node.dataset.tip;
        tipText.textContent = msg;
        const pt = svg.createSVGPoint ? svg.createSVGPoint() : null;
        let x = 0, y = 0;
        if (pt) {
          pt.x = e.clientX; pt.y = e.clientY;
          const local = pt.matrixTransform(svg.getScreenCTM().inverse());
          x = local.x; y = local.y;
        } else {
          const box = svg.getBoundingClientRect();
          x = e.clientX - box.left; y = e.clientY - box.top;
        }
        const w = Math.min(msg.length * 6.4 + 20, 420);
        const px = Math.max(0, Math.min(x + 8, 680 - w));
        tipRect.setAttribute("x", px);
        tipRect.setAttribute("y", y - 34);
        tipRect.setAttribute("width", w);
        tipRect.setAttribute("height", 24);
        tipText.setAttribute("x", px + 10);
        tipText.setAttribute("y", y - 18);
        tip.setAttribute("visibility", "visible");
      });
      node.addEventListener("mouseleave", function () {
        tip.setAttribute("visibility", "hidden");
      });
    });
  }
});
