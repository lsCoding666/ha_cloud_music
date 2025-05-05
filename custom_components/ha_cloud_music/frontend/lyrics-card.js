console.log('Loading lyrics-card.js');

class LyricsCardEditor extends HTMLElement {
    constructor() {
        super();
        this._config = {};
    }

    setConfig(config) {
        console.log('Entering setConfig method of', this.constructor.name);
        this._config = JSON.parse(JSON.stringify(config)) || {};
        this._render();
    }

    set hass(hass) {
        if (this._hass === hass) return;
        console.log('Entering hass setter of', this.constructor.name);
        this._hass = hass;
        // this._render();
    }

    _render() {
        console.log('Entering _render method of', this.constructor.name);
        if (!this._hass) return;

        this.innerHTML = `
            <div class="card-config">
                <div class="form-group">
                    <label>选择媒体播放器：</label>
                    <select class="entity-selector">
                        <option value="">请选择...</option>
                        ${Object.keys(this._hass.states)
                            .filter(entityId => entityId.startsWith('media_player.'))
                            .map(entityId => {
                                const state = this._hass.states[entityId];
                                const name = state.attributes.friendly_name || entityId;
                                return `<option value="${entityId}" ${this._config.entity === entityId ? 'selected' : ''}>${name}</option>`;
                            })
                            .join('')}
                    </select>
                </div>
            </div>
            <style>
                .card-config {
                    padding: 16px;
                }
                .form-group {
                    margin-bottom: 16px;
                }
                label {
                    display: block;
                    margin-bottom: 8px;
                }
                select {
                    width: 100%;
                    padding: 8px;
                    border-radius: 4px;
                    border: 1px solid var(--divider-color);
                    background-color: var(--card-background-color);
                    color: var(--primary-text-color);
                }
            </style>
        `;

         // 手动绑定事件监听器
         const select = this.querySelector('.entity-selector');
         select.addEventListener('change', (ev) => this._valueChanged(ev));
    }

    _valueChanged(ev) {
        this._config = { ...this._config, entity: ev.target.value };
        this.dispatchEvent(new CustomEvent('config-changed', {
            detail: { config: this._config }
        }));
    }
}

customElements.define('lyrics-card-editor', LyricsCardEditor);
console.log('Registered lyrics-card-editor');

class LyricsCard extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        this._config = {};
        this._previousLyric = '';
        this._currentLyric = '';
        this._nextLyric = '';
        this._lyricsHistory = [];
        this._animationFrame = null;
    }

    setConfig(config) {
        this._config = config;
        this._render();
    }
    

    _render() {
        console.log('Entering _render method of', this.constructor.name);
        this.shadowRoot.innerHTML = `
            <ha-card>
                <div class="lyrics-container">
                    <div class="lyrics-wrapper">
                        <div class="previous-lyric"></div>
                        <div class="current-lyric"></div>
                        <div class="next-lyric"></div>
                    </div>
                </div>
            </ha-card>
            <style>
                :host {
                    display: block;
                    height: 100%;
                }
                ha-card {
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    background: var(--card-background-color, #fff);
                    border-radius: 12px;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                }
                .lyrics-container {
                    padding: 12px;
                    text-align: center;
                    flex: 1;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }
                .lyrics-wrapper {
                    position: relative;
                    width: 100%;
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    gap: 8px;
                }
                .previous-lyric,
                .current-lyric,
                .next-lyric {
                    width: 100%;
                    text-align: center;
                    transition: all 0.3s ease;
                    line-height: 1.4;
                    color: var(--secondary-text-color);
                    padding: 4px 0;
                    min-height: 32px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }
                .current-lyric {
                    color: var(--primary-text-color);
                    font-size: 1.3em;
                    font-weight: 500;
                    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
                }
                .previous-lyric,
                .next-lyric {
                    opacity: 0.6;
                    font-size: 1.1em;
                }
                @keyframes fadeIn {
                    from { 
                        opacity: 0; 
                        transform: translateY(10px); 
                    }
                    to { 
                        opacity: 1; 
                        transform: translateY(0); 
                    }
                }
                .lyric-enter {
                    animation: fadeIn 0.3s ease forwards;
                }
            </style>
        `;

        this.currentLyric = this.shadowRoot.querySelector('.current-lyric');
        this.previousLyric = this.shadowRoot.querySelector('.previous-lyric');
        this.nextLyric = this.shadowRoot.querySelector('.next-lyric');
        
        if (this._hass) {
            this.updateContent();
        }
    }

    set hass(hass) {
        this._hass = hass;
        this.updateContent();
    }

    updateContent() {
        if (!this._hass) return;

        const entity = this._hass.states[this._config.entity];
        if (!entity) return;

        const currentLyric = entity.attributes.current_lyric || '';
        const nextLyric = entity.attributes.next_lyric;
        const mediaTitle = entity.attributes.media_title || '';
        const mediaArtist = entity.attributes.media_artist || '';
        
        if (currentLyric && currentLyric !== this._currentLyric) {
            console.log('Updating lyrics:', {
                previous: this._previousLyric,
                current: currentLyric,
                next: nextLyric
            });

            // 更新歌词显示
            this._previousLyric = this._currentLyric;
            this._currentLyric = currentLyric;
            this._nextLyric = nextLyric;
            
            // 更新DOM
            if (this._previousLyric) {
                this.previousLyric.textContent = this._previousLyric;
            } else {
                this.previousLyric.textContent = `${mediaTitle} - ${mediaArtist}`;
            }
            
            this.currentLyric.textContent = this._currentLyric;
            this.nextLyric.textContent = this._nextLyric || '';
            
            // 添加动画效果
            this.currentLyric.classList.remove('lyric-enter');
            void this.currentLyric.offsetWidth; // 触发重绘
            this.currentLyric.classList.add('lyric-enter');
        }
    }

    getCardSize() {
        return 3;
    }

    static getStubConfig() {
        return {
            entity: this._config?.entity,
            type: 'custom:lyrics-card'
        };
    }

    static getConfigElement() {
    return document.createElement('lyrics-card-editor');
}

}

customElements.define('lyrics-card', LyricsCard);
console.log('Registered lyrics-card');

// 注册自定义卡片
window.customCards = window.customCards || [];
window.customCards.push({
    type: 'lyrics-card',
    name: 'Lyrics Card',
    description: 'A card to display synchronized lyrics for music players',
    preview: true,
    documentationURL: 'https://github.com/shaonianzhentan/ha_cloud_music'
});
console.log('Registered custom card');