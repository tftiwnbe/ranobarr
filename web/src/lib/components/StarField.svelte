<script lang="ts">
  interface Props {
    count?: number;
  }

  let { count = 40 }: Props = $props();

  function prng(seed: number) {
    return () => {
      seed |= 0;
      seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function generateStars(n: number) {
    const rand = prng(42);
    return Array.from({ length: n }, () => {
      const bright = rand() < 0.15;
      return {
        x: rand() * 100,
        y: rand() * 100,
        size: bright ? 2 + rand() * 1.6 : 1 + rand() * 1.2,
        opacity: bright ? 0.6 + rand() * 0.3 : 0.14 + rand() * 0.3,
        duration: 2.5 + rand() * 4,
        delay: rand() * 6,
        bright
      };
    });
  }

  const stars = $derived.by(() => generateStars(count));
</script>

<div class="starfield-layer" style="position:fixed;inset:0;overflow:hidden;pointer-events:none;z-index:0;">
  {#each stars as star, i (i)}
    <div
      style={`position:absolute;left:${star.x}%;top:${star.y}%;width:${star.size}px;height:${star.size}px;border-radius:999px;background:${star.bright ? "var(--text)" : "var(--text-soft)"};opacity:${star.opacity};box-shadow:0 0 ${star.bright ? 8 : 4}px ${star.bright ? "rgba(255,255,255,0.5)" : "rgba(200,200,210,0.15)"};animation:${star.bright ? "twinkle" : "twinkle-slow"} ${star.duration}s ease-in-out infinite;animation-delay:${star.delay}s;`}
    ></div>
  {/each}
</div>
