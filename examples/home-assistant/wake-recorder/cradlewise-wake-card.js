class CradlewiseWakeClipsCard extends HTMLElement {
  setConfig(config) {
    if (!config.media_content_id) {
      throw new Error("media_content_id is required");
    }

    this.config = {
      title: "Wake Clips",
      limit: 8,
      refresh_seconds: 300,
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._loaded && !this._loading) {
      this._loadClips();
    }
  }

  connectedCallback() {
    this._startRefreshTimer();
  }

  disconnectedCallback() {
    window.clearInterval(this._refreshTimer);
  }

  getCardSize() {
    return 6;
  }

  _startRefreshTimer() {
    window.clearInterval(this._refreshTimer);
    if (!this.config) {
      return;
    }
    const refreshMilliseconds = this.config.refresh_seconds * 1000;
    this._refreshTimer = window.setInterval(
      () => {
        const videos = [...(this.shadowRoot?.querySelectorAll("video") || [])];
        if (videos.every((video) => video.paused)) {
          this._loadClips();
        }
      },
      refreshMilliseconds,
    );
  }

  async _loadClips() {
    if (!this._hass || this._loading) {
      return;
    }

    this._loading = true;
    this._renderLoading();

    try {
      const directory = await this._hass.callWS({
        type: "media_source/browse_media",
        media_content_id: this.config.media_content_id,
      });
      const clips = (directory.children || [])
        .filter((item) => item.can_play && item.media_class === "video")
        .sort((left, right) => right.title.localeCompare(left.title))
        .slice(0, this.config.limit);
      const resolvedClips = await Promise.all(
        clips.map(async (clip) => {
          const media = await this._hass.callWS({
            type: "media_source/resolve_media",
            media_content_id: clip.media_content_id,
          });
          return {...clip, url: this._hass.hassUrl(media.url)};
        }),
      );

      this._loaded = true;
      this._renderClips(resolvedClips);
    } catch (error) {
      this._renderError(error);
    } finally {
      this._loading = false;
    }
  }

  _ensureRoot() {
    if (!this.shadowRoot) {
      this.attachShadow({mode: "open"});
    }
    this.shadowRoot.replaceChildren();

    const card = document.createElement("ha-card");
    card.header = this.config.title;
    this.shadowRoot.append(card, this._styleElement());
    return card;
  }

  _renderLoading() {
    const card = this._ensureRoot();
    const message = document.createElement("div");
    message.className = "message";
    message.textContent = "Loading wake clips...";
    card.append(message);
  }

  _renderError(error) {
    const card = this._ensureRoot();
    const message = document.createElement("div");
    message.className = "message error";
    message.textContent = `Unable to load wake clips: ${error.message}`;
    card.append(message);
  }

  _renderClips(clips) {
    const card = this._ensureRoot();

    if (!clips.length) {
      const message = document.createElement("div");
      message.className = "message";
      message.textContent = "No wake clips yet.";
      card.append(message);
      return;
    }

    const grid = document.createElement("div");
    grid.className = "grid";
    for (const clip of clips) {
      const article = document.createElement("article");
      const video = document.createElement("video");
      const label = document.createElement("div");

      video.controls = true;
      video.preload = "metadata";
      video.src = clip.url;
      label.className = "label";
      label.textContent = this._clipLabel(clip.title);
      article.append(video, label);
      grid.append(article);
    }
    card.append(grid);
  }

  _clipLabel(filename) {
    const match = filename.match(
      /^cradlewise_wake_(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})\.mp4$/,
    );
    if (!match) {
      return filename;
    }

    const [, year, month, day, hour, minute, second] = match;
    const timestamp = new Date(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hour),
      Number(minute),
      Number(second),
    );
    return timestamp.toLocaleString([], {
      dateStyle: "medium",
      timeStyle: "short",
    });
  }

  _styleElement() {
    const style = document.createElement("style");
    style.textContent = `
      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
        gap: 12px;
        padding: 0 16px 16px;
      }
      article {
        overflow: hidden;
        border: 1px solid var(--divider-color);
        border-radius: var(--ha-card-border-radius, 12px);
        background: var(--card-background-color);
      }
      video {
        display: block;
        width: 100%;
        aspect-ratio: 16 / 9;
        background: #000;
      }
      .label {
        padding: 10px 12px;
        color: var(--primary-text-color);
        font-size: 13px;
        font-weight: 500;
      }
      .message {
        padding: 0 16px 16px;
        color: var(--secondary-text-color);
      }
      .error {
        color: var(--error-color);
      }
    `;
    return style;
  }
}

customElements.define(
  "cradlewise-wake-clips-card",
  CradlewiseWakeClipsCard,
);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "cradlewise-wake-clips-card",
  name: "Cradlewise Wake Clips",
  description: "Authenticated gallery of Cradlewise wake recordings.",
});
