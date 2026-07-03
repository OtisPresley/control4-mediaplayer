class Control4Card extends HTMLElement {
  setConfig(config) {
    // Make a shallow copy because HA freezes the config object,
    // which throws "Cannot add property favorites, object is not extensible"
    this._config = { ...config };
    
    // Load favorites from local storage if not in config
    if (!this._config.favorites) {
      this._config.favorites = JSON.parse(localStorage.getItem('control4_favorites') || '[]');
    }
    
    this._prevPlayingStates = {};
    this._optimisticSources = {};
    this._optimisticMutes = {};
    this._optimisticVolumes = {};
  }

  static getConfigElement() {
    return document.createElement("control4-card-editor");
  }

  set hass(hass) {
    this._hass = hass;
    
    // Fetch entity registry to find entities by platform
    if (!this._entityReg && !this._fetchingReg && hass && typeof hass.callWS === 'function') {
      this._fetchingReg = true;
      hass.callWS({ type: "config/entity_registry/list" })
        .then(r => {
          this._entityReg = r;
          this._fetchingReg = false;
          this.render();
        })
        .catch(e => {
          console.error("Failed to get entity registry", e);
          this._entityReg = [];
          this._fetchingReg = false;
          this.render();
        });
    }
    
    // Clear optimistic states that match the actual state
    if (hass) {
      for (const id in this._optimisticSources) {
        if (hass.states[id]?.attributes?.source === this._optimisticSources[id]) {
          delete this._optimisticSources[id];
        }
      }
      for (const id in this._optimisticMutes) {
        if (hass.states[id]?.attributes?.is_volume_muted === this._optimisticMutes[id]) {
          delete this._optimisticMutes[id];
        }
      }
      for (const id in this._optimisticVolumes) {
        const actualVol = Math.round((hass.states[id]?.attributes?.volume_level || 0) * 100);
        if (actualVol === this._optimisticVolumes[id]) {
          delete this._optimisticVolumes[id];
        }
      }
    }
    
    // Auto-detect playing source and switch zone/input
    // this.autoDetectPlaying();
    
    this.render();
  }

  autoDetectPlaying() {
    if (!this._hass || !this._config.mappings) return;
    
    // Don't auto-switch if the user is actively interacting with the card
    if (this._userInteracting) return;
    
    const mappings = this._config.mappings;
    
    for (const [inputName, playerId] of Object.entries(mappings)) {
      const playerState = this._hass.states[playerId];
      const isPlaying = playerState && (playerState.state === 'playing' || playerState.state === 'on');
      const wasPlaying = this._prevPlayingStates[playerId] || false;
      
      // Update state for next check
      this._prevPlayingStates[playerId] = isPlaying;
      
      // Only auto-switch if it JUST started playing (edge detection)
      // or if it's the first run and something is playing.
      const isNewPlay = isPlaying && !wasPlaying;
      const isFirstRun = this._isFirstAutoDetect === undefined;
      
      if (isNewPlay || (isFirstRun && isPlaying)) {
        // Find which zone has this input selected
        const selectedZoneSourceList = this._hass.states[this.selectedZoneId]?.attributes?.source_list || [];
        const zones = Object.keys(this._hass.states).filter(id => {
          if (!id.startsWith('media_player.')) return false;
          const state = this._hass.states[id];
          return state && JSON.stringify(state.attributes.source_list || []) === JSON.stringify(selectedZoneSourceList);
        });
        
        for (const zoneId of zones) {
          const zoneState = this._hass.states[zoneId];
          if (zoneState && zoneState.attributes.source === inputName) {
            if (this.selectedZoneId !== zoneId || this.selectedInputName !== inputName) {
              this.selectedZoneId = zoneId;
              this.selectedInputName = inputName;
              this.render(true);
            }
            return;
          }
        }
      }
    }
  }

  getChannel(zoneId) {
    if (!this._entityReg) return null;
    const entry = this._entityReg.find(e => e.entity_id === zoneId);
    if (entry && entry.unique_id) {
      const match = entry.unique_id.match(/_ch(\d+)$/);
      return match ? match[1] : null;
    }
    return null;
  }

  findEntityByUniqueId(pattern) {
    if (!this._entityReg) return null;
    const entry = this._entityReg.find(e => e.unique_id && e.unique_id.includes(pattern));
    return entry ? entry.entity_id : null;
  }

  render(force = false) {
    try {
      if (!this._hass) return;
      
      // Avoid blowing away innerHTML if the card is already rendered,
      // which causes dropdowns to close while the user is interacting.
      if (!force && this.querySelector('#zone-select')) {
        this.updateVolatileStates();
        return;
      }
      
      // 1. Find zones
      let zones = [];
      if (this._entityReg) {
        const integrationEntities = this._entityReg.filter(e => e.platform === 'control4_mediaplayer');
        
        zones = integrationEntities
          .filter(e => e.entity_id.startsWith('media_player.'))
          .map(e => e.entity_id)
          .filter(id => id in this._hass.states); // Ensure entity exists in current states
      }
      
      // Fallback
      if (zones.length === 0 && !this._entityReg) {
        const refZone = this._config?.default_zone || Object.keys(this._hass.states).find(id => id.startsWith('media_player.') && this._hass.states[id].attributes.source_list);
        const refSourceList = refZone ? this._hass.states[refZone].attributes.source_list : [];
        zones = Object.keys(this._hass.states).filter(id => {
          if (!id.startsWith('media_player.')) return false;
          const state = this._hass.states[id];
          return state && JSON.stringify(state.attributes.source_list || []) === JSON.stringify(refSourceList);
        });
      }
      
      if (zones.length === 0) {
        this.innerHTML = `
          <ha-card style="padding: 16px;">
            <div style="color: var(--secondary-text-color);">No Control4 zones found.</div>
          </ha-card>
        `;
        return;
      }
      
      // Helper to find longest common prefix
      const longestCommonPrefix = (strs) => {
        if (!strs.length) return "";
        let prefix = strs[0];
        for (let i = 1; i < strs.length; i++) {
          while (strs[i].indexOf(prefix) !== 0) {
            prefix = prefix.substring(0, prefix.length - 1);
            if (!prefix) return "";
          }
        }
        return prefix;
      };

      // Get all friendly names to find common prefix
      const zoneNames = zones.map(id => this._hass.states[id]?.attributes?.friendly_name || id);
      const commonPrefix = longestCommonPrefix(zoneNames);
      
      const getShortName = (name) => {
        if (commonPrefix && commonPrefix.length < name.length) {
          return name.substring(commonPrefix.length).replace(/^\d+\s+/, '');
        }
        return name.replace(/^\d+\s+/, '');
      };

      // Ensure selected zone is valid
      if (!this.selectedZoneId || !zones.includes(this.selectedZoneId)) {
        this.selectedZoneId = this._config?.default_zone || zones[0];
      }
      
      const selectedZoneState = this._hass.states[this.selectedZoneId];
      const inputs = selectedZoneState?.attributes?.source_list || [];
      
      if (!this.selectedInputName || !inputs.includes(this.selectedInputName)) {
        this.selectedInputName = selectedZoneState?.attributes?.source || (inputs.length > 0 ? inputs[0] : '');
      }
      
      // Helper to get volume (including optimistic)
      const getZoneVol = (id) => this._optimisticVolumes[id] !== undefined ? this._optimisticVolumes[id] : Math.round((this._hass.states[id]?.attributes?.volume_level || 0) * 100);
      
      const vol = getZoneVol(this.selectedZoneId);
      
      // Helper to get mute state (including optimistic)
      const getZoneMute = (id) => this._optimisticMutes[id] !== undefined ? this._optimisticMutes[id] : this._hass.states[id]?.attributes?.is_volume_muted || false;
      
      const isMuted = getZoneMute(this.selectedZoneId);
      const isOn = selectedZoneState?.state === 'on' || selectedZoneState?.state === 'playing';
      
      // Get mapped player for media info
      const mappedPlayerId = this._config?.mappings?.[this.selectedInputName];
      const mappedPlayerState = mappedPlayerId ? this._hass.states[mappedPlayerId] : null;
      const artwork = mappedPlayerState?.attributes?.entity_picture;
      
      // Get favorites from local storage or config
      const favorites = this._config.favorites || [];
      
      // Helper to get source (including optimistic)
      const getZoneSource = (id) => this._optimisticSources[id] || this._hass.states[id]?.attributes?.source;
      
      // Find joined zones for volume controls
      const joinedZones = zones.filter(id => id !== this.selectedZoneId && getZoneSource(id) === this.selectedInputName);
      
      
      // 2. Render UI with dropdowns and Glassmorphism
      this.innerHTML = `
        <style>
          .glass-card {
            --text-color: var(--primary-text-color, white);
            --text-color-secondary: var(--secondary-text-color, rgba(255, 255, 255, 0.5));
            --text-color-disabled: var(--disabled-text-color, rgba(255, 255, 255, 0.3));
            --card-bg: var(--ha-card-background, var(--card-background-color, rgba(255, 255, 255, 0.05)));
            --border-color: var(--ha-card-border-color, rgba(255, 255, 255, 0.1));
            --glass-bg: rgba(var(--rgb-primary-text-color, 255, 255, 255), 0.05);
            --glass-bg-hover: rgba(var(--rgb-primary-text-color, 255, 255, 255), 0.1);
            --glass-bg-active: rgba(var(--rgb-primary-text-color, 255, 255, 255), 0.15);
            --select-arrow: url("data:image/svg+xml;utf8,<svg fill='gray' height='24' viewBox='0 0 24 24' width='24' xmlns='http://www.w3.org/2000/svg'><path d='M7 10l5 5 5-5z'/><path d='M0 0h24v24H0z' fill='none'/></svg>");
            
            position: relative;
            background: var(--card-bg) !important;
            backdrop-filter: blur(10px) !important;
            -webkit-backdrop-filter: blur(10px) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: var(--ha-card-border-radius, 16px) !important;
            padding: 20px !important;
            color: var(--text-color) !important;
            box-shadow: var(--ha-card-box-shadow, 0 8px 32px 0 rgba(0, 0, 0, 0.37)) !important;
            overflow: hidden;
          }
          
          .glass-card.has-artwork {
            --text-color: white;
            --text-color-secondary: rgba(255, 255, 255, 0.6);
            --text-color-disabled: rgba(255, 255, 255, 0.3);
            --card-bg: rgba(0, 0, 0, 0.25);
            --border-color: rgba(255, 255, 255, 0.1);
            --glass-bg: rgba(255, 255, 255, 0.05);
            --glass-bg-hover: rgba(255, 255, 255, 0.15);
            --glass-bg-active: rgba(255, 255, 255, 0.2);
            --select-arrow: url("data:image/svg+xml;utf8,<svg fill='white' height='24' viewBox='0 0 24 24' width='24' xmlns='http://www.w3.org/2000/svg'><path d='M7 10l5 5 5-5z'/><path d='M0 0h24v24H0z' fill='none'/></svg>");
          }
          
          .card-bg {
            position: absolute;
            top: -20px; left: -20px; right: -20px; bottom: -20px;
            background-image: url('${artwork || ''}');
            background-size: cover;
            background-position: center;
            filter: blur(40px) brightness(0.4);
            z-index: 0;
            display: ${artwork ? 'block' : 'none'};
          }
          
          .card-content {
            position: relative;
            z-index: 1;
          }
          
          .card-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 24px;
          }
          
          .glass-label {
            display: block;
            margin-bottom: 6px;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: var(--text-color-secondary);
          }
          
          .glass-select {
            width: 100%;
            padding: 12px;
            background: var(--glass-bg) !important;
            color: var(--text-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 8px !important;
            font-size: 14px;
            backdrop-filter: blur(5px);
            -webkit-backdrop-filter: blur(5px);
            cursor: pointer;
            appearance: none;
            -webkit-appearance: none;
            background-image: var(--select-arrow);
            background-repeat: no-repeat;
            background-position-x: 98%;
            background-position-y: 50%;
            transition: border 0.3s;
          }
          
          .glass-select:focus {
            border: 1px solid var(--text-color-secondary) !important;
            outline: none;
          }
          
          .glass-select option {
            background: var(--card-background-color, #2c2c2c);
            color: var(--primary-text-color, white);
          }
          
          .glass-card.has-artwork .glass-select option {
            background: #2c2c2c;
            color: white;
          }
          
          .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
          }
          
          .power-btn {
            background: none;
            border: none;
            color: ${isOn ? '#03a9f4' : 'var(--text-color-disabled)'};
            cursor: pointer;
            padding: 8px;
            border-radius: 50%;
            background: var(--glass-bg);
            display: flex;
            align-items: center;
            justify-content: center;
          }
          
          .vol-container {
            display: flex;
            flex-direction: column;
            align-items: stretch;
            background: var(--glass-bg);
            padding: 10px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            min-width: 0; /* Prevent grid overflow */
          }
          
          .vol-title {
            font-size: 12px;
            font-weight: bold;
            margin-bottom: 4px;
            color: var(--text-color);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          
          .vol-control-row {
            display: flex;
            align-items: center;
            gap: 8px;
            white-space: nowrap;
          }
          
          .vol-slider {
            flex: 1;
            margin: 0;
            accent-color: #03a9f4;
            min-width: 50px; /* Prevent slider from vanishing */
          }
          
          .vol-percentage {
            font-size: 13px;
            width: 35px;
            text-align: right;
            color: var(--text-color-secondary);
            flex-shrink: 0; /* Prevent percentage from shrinking */
          }
          
          .fav-chip {
            background: var(--glass-bg);
            padding: 6px 12px;
            border-radius: 16px;
            font-size: 12px;
            color: var(--text-color);
            cursor: pointer;
            display: flex;
            align-items: center;
            border: 1px solid var(--border-color);
            transition: all 0.3s ease;
          }
          
          .fav-chip:hover {
            background: var(--glass-bg-hover);
            transform: translateY(-1px);
          }
          
          .player-controls {
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-top: 15px;
          }
          
          .control-btn {
            background: none;
            border: none;
            color: var(--text-color);
            cursor: pointer;
            padding: 10px;
            border-radius: 50%;
            background: var(--glass-bg);
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
            width: 40px;
            height: 40px;
          }
          
          .control-btn:hover {
            background: var(--glass-bg-hover);
            transform: scale(1.05);
          }
          
          .col-section {
            display: flex;
            flex-direction: column;
            gap: 16px;
          }
          
          .zone-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
            gap: 8px;
            background: var(--glass-bg);
            padding: 12px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
          }
          
          .zone-chip {
            background: var(--glass-bg);
            padding: 8px;
            border-radius: 6px;
            font-size: 12px;
            color: var(--text-color);
            cursor: pointer;
            text-align: center;
            border: 1px solid var(--border-color);
            transition: all 0.2s;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
          }
          
          .zone-chip.joined {
            background: rgba(3, 169, 244, 0.2);
            border: 1px solid rgba(3, 169, 244, 0.4);
            color: #03a9f4;
            font-weight: bold;
          }
          
          .zone-chip:hover {
            background: var(--glass-bg-hover);
          }
          
          .zone-chip.joined:hover {
            background: rgba(3, 169, 244, 0.3);
          }
          
          .vol-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 8px;
            margin-top: 8px;
          }
          
          .manual-fav-form {
            display: flex;
            flex-direction: column;
            gap: 8px;
            background: var(--glass-bg);
            padding: 12px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
            margin-bottom: 12px;
          }
          
          .manual-fav-form input, .manual-fav-form select {
            width: 100%;
            padding: 8px;
            background: var(--glass-bg) !important;
            color: var(--text-color) !important;
            border: 1px solid var(--border-color) !important;
            border-radius: 4px !important;
            font-size: 13px;
            box-sizing: border-box !important;
          }
          
          .manual-fav-form button {
            width: 100%;
            padding: 10px;
            background: #03a9f4;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-weight: bold;
            font-size: 13px;
            transition: background 0.2s;
            box-sizing: border-box !important;
          }
          
          .manual-fav-form select option {
            background: var(--card-background-color, #2c2c2c) !important;
            color: var(--primary-text-color, white) !important;
          }
          
          .glass-card.has-artwork .manual-fav-form select option {
            background: #2c2c2c !important;
            color: white !important;
          }
          

        </style>

        <ha-card class="glass-card ${artwork ? 'has-artwork' : ''}">
          <div class="card-bg"></div>
          
          <div class="card-content">
            <div class="header">
              <div style="font-size: 18px; font-weight: bold; letter-spacing: 1px;">${this._config.title || 'Control4 Command Center'}</div>
              <button id="power-btn" class="power-btn" title="Toggle Power">
                <ha-icon icon="mdi:power"></ha-icon>
              </button>
            </div>
            
            <div class="card-grid">
              <!-- Left Column: Now Playing & Controls -->
              <div class="col-section">
                <!-- Media Info -->
                <div id="media-info-container">
                  ${mappedPlayerState ? `
                    <div style="background: var(--glass-bg); padding: 16px; border-radius: 12px; position: relative; border: 1px solid var(--border-color);">
                      <div style="display: flex; align-items: center;">
                        <div class="media-artwork" style="margin-right: 16px;">
                          ${artwork ? `
                            <img src="${artwork}" style="width: 70px; height: 70px; border-radius: 8px; object-fit: cover; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
                          ` : `
                            <div style="width: 70px; height: 70px; border-radius: 8px; background: var(--glass-bg); display: flex; align-items: center; justify-content: center;">
                              <ha-icon icon="mdi:music" style="color: var(--text-color-disabled); font-size: 30px;"></ha-icon>
                            </div>
                          `}
                        </div>
                        <div style="flex: 1; min-width: 0; padding-right: 70px;">
                          <div class="media-title" style="font-weight: bold; font-size: 15px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 4px;">${mappedPlayerState.attributes.media_title || 'Unknown Title'}</div>
                          <div class="media-artist" style="font-size: 13px; color: var(--text-color-secondary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px;">${mappedPlayerState.attributes.media_artist || 'Unknown Artist'}</div>
                          <div style="font-size: 11px; color: var(--text-color-disabled);">via ${mappedPlayerState.attributes.friendly_name || mappedPlayerId}</div>
                        </div>
                        <div style="position: absolute; right: 12px; top: 12px; display: flex; gap: 8px;">

                          <button id="browse-btn" style="background: none; border: none; color: var(--text-color-secondary); cursor: pointer; padding: 2px;" title="Browse Media">
                            <ha-icon icon="mdi:folder-music"></ha-icon>
                          </button>
                          <button id="fav-btn" style="background: none; border: none; color: var(--text-color-secondary); cursor: pointer; padding: 2px;" title="Save as Favorite">
                            <ha-icon icon="mdi:star-outline"></ha-icon>
                          </button>
                        </div>
                      </div>
                      
                      <!-- Source Player Controls -->
                      <div class="player-controls">
                        <button class="control-btn" id="prev-btn" title="Previous"><ha-icon icon="mdi:skip-previous"></ha-icon></button>
                        <button class="control-btn" id="play-btn" style="width: 46px; height: 46px; background: var(--glass-bg-active);" title="Play/Pause"><ha-icon icon="${mappedPlayerState.state === 'playing' ? 'mdi:pause' : 'mdi:play'}"></ha-icon></button>
                        <button class="control-btn" id="next-btn" title="Next"><ha-icon icon="mdi:skip-next"></ha-icon></button>
                      </div>
                    </div>
                  ` : `
                    <div style="text-align: center; color: var(--text-color-disabled); font-size: 13px; padding: 20px; background: var(--glass-bg); border-radius: 12px; border: 1px solid var(--border-color); position: relative;">
                      No player mapped for this input.
                      <div style="position: absolute; right: 12px; top: 12px;">

                      </div>
                    </div>
                  `}
                </div>
                
                <!-- Volume -->
                <div>
                  <label class="glass-label">Volume</label>
                  
                  <div class="vol-grid">
                    <!-- Main Zone Volume -->
                    <div class="vol-container">
                      <div class="vol-title">
                        ${getShortName(this._hass.states[this.selectedZoneId]?.attributes?.friendly_name || 'Main Zone')}
                      </div>
                      <div class="vol-control-row">
                        <button id="mute-btn" style="background:none; border:none; color: var(--text-color); cursor:pointer; padding:2px; display:flex; align-items:center;">
                          <ha-icon icon="${isMuted ? 'mdi:volume-off' : 'mdi:volume-high'}" style="font-size: 20px;"></ha-icon>
                        </button>
                        <input id="volume-slider" class="vol-slider" type="range" min="0" max="100" value="${vol}">
                        <span id="vol-text" class="vol-percentage">${vol}%</span>
                      </div>
                    </div>
                    
                    <!-- Linked Zones Volume -->
                    ${joinedZones.map(id => {
                      const zoneState = this._hass.states[id];
                      const zVol = getZoneVol(id);
                      const zMuted = getZoneMute(id);
                      const name = zoneState?.attributes?.friendly_name || id;
                      const shortName = getShortName(name);
                      
                      return `
                        <div class="vol-container">
                          <div class="vol-title">${shortName}</div>
                          <div class="vol-control-row">
                            <button class="linked-mute-btn" data-zone="${id}" style="background:none; border:none; color: var(--text-color); cursor:pointer; padding:2px; display:flex; align-items:center;">
                              <ha-icon icon="${zMuted ? 'mdi:volume-off' : 'mdi:volume-high'}" style="font-size: 20px;"></ha-icon>
                            </button>
                            <input class="linked-vol-slider" data-zone="${id}" type="range" min="0" max="100" value="${zVol}" style="flex: 1; margin: 0; accent-color: #03a9f4; min-width: 50px;">
                            <span class="vol-percentage">${zVol}%</span>
                          </div>
                        </div>
                      `;
                    }).join('')}
                  </div>
                </div>
              </div>
              
              <!-- Right Column: Selection & Favorites -->
              <div class="col-section">
                <!-- Zone & Input Selection -->
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                  <div>
                    <label class="glass-label">Zone</label>
                    <select id="zone-select" class="glass-select">
                      ${zones.map(id => `<option value="${id}" ${id === this.selectedZoneId ? 'selected' : ''}>${this._hass.states[id].attributes.friendly_name || id}</option>`).join('')}
                    </select>
                  </div>
                  <div>
                    <label class="glass-label">Input</label>
                    <select id="input-select" class="glass-select">
                      ${inputs.map(input => `<option value="${input}" ${input === this.selectedInputName ? 'selected' : ''}>${input}</option>`).join('')}
                    </select>
                  </div>
                </div>
                
                <!-- Zone Joining (Add/Remove Zones) -->
                <div>
                  <label class="glass-label">Linked Zones (Join)</label>
                  <div class="zone-grid">
                    ${zones.filter(id => id !== this.selectedZoneId).map(id => {
                      const isJoined = getZoneSource(id) === this.selectedInputName;
                      const zoneState = this._hass.states[id];
                      const name = zoneState?.attributes?.friendly_name || id;
                      const shortName = getShortName(name);
                      return `
                        <div class="zone-chip ${isJoined ? 'joined' : ''}" data-zone="${id}">
                          ${shortName}
                        </div>
                      `;
                    }).join('')}
                    ${zones.length <= 1 ? `<div style="font-size: 11px; color: var(--text-color-disabled); grid-column: 1 / -1; text-align: center;">No other zones available.</div>` : ''}
                  </div>
                </div>
                
                <!-- Favorites Section -->
                <div>
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <label class="glass-label" style="margin-bottom: 0;">Favorites</label>
                    <button id="toggle-manual-fav" style="background: none; border: none; color: var(--text-color-secondary); cursor: pointer; display: flex; align-items: center;" title="Add Manual Favorite">
                      <ha-icon icon="mdi:plus" style="font-size: 20px;"></ha-icon>
                    </button>
                  </div>
                  
                  <!-- Manual Favorite Form (Hidden by default) -->
                  <div id="manual-fav-form" class="manual-fav-form" style="display: none;">
                    <input id="manual-fav-name" placeholder="Favorite Name (e.g. NPR)">
                    <select id="manual-fav-input" title="Select Input/Player">
                      ${inputs.map(input => `<option value="${input}" ${input === this.selectedInputName ? 'selected' : ''}>Target: ${input}</option>`).join('')}
                    </select>
                    <input id="manual-fav-cmd" placeholder="Command (e.g. play NPR)">
                    <button id="save-manual-fav">Save Favorite</button>
                  </div>
                  
                  <div id="fav-chips-container" style="display: flex; flex-wrap: wrap; gap: 6px;">
                    ${favorites.map((fav, index) => `
                      <div class="fav-chip" data-index="${index}">
                        <span>${fav.name}</span>
                        <ha-icon icon="mdi:close" style="font-size: 14px; margin-left: 6px; opacity: 0.4;" data-action="delete" data-index="${index}"></ha-icon>
                      </div>
                    `).join('')}
                    ${(favorites.length === 0) ? `
                      <div style="font-size: 12px; color: var(--text-color-disabled); padding: 10px; text-align: center; background: var(--glass-bg); border-radius: 8px; width: 100%;">No favorites saved yet.</div>
                    ` : ''}
                  </div>
                </div>
              </div>
            </div> <!-- End Grid -->
            
          </div>
        </ha-card>
      `;
      
      // 3. Bind events
      this.setupEvents();
      
    } catch (e) {
      this.innerHTML = `
        <ha-card style="padding: 16px; color: red;">
          <h3>Render Error</h3>
          <pre>${e.message}</pre>
        </ha-card>
      `;
    }
  }
  
  setupEvents() {
    if (this._eventsSetup) return;
    this._eventsSetup = true;
    
    this.addEventListener('change', (ev) => {
      if (ev.target.id === 'zone-select') {
        this.selectedZoneId = ev.target.value;
        const newState = this._hass.states[this.selectedZoneId];
        // Automatically switch Input dropdown to the input it is currently on
        this.selectedInputName = newState?.attributes?.source || '';
        this.render(true); // Force re-render to update inputs
      } else if (ev.target.id === 'input-select') {
        this.selectedInputName = ev.target.value;
        
        // Mark as user interacting to prevent auto-detect from fighting back
        this._userInteracting = true;
        if (this._interactTimeout) clearTimeout(this._interactTimeout);
        this._interactTimeout = setTimeout(() => { this._userInteracting = false; }, 10000); // 10 sec buffer
        
        // Immediately set source on amp
        this._hass.callService('media_player', 'select_source', {
          entity_id: this.selectedZoneId,
          source: this.selectedInputName
        });
        
        this.render(true); // Force re-render to update media info
      } else if (ev.target.id === 'volume-slider') {
        const value = parseInt(ev.target.value);
        this._optimisticVolumes[this.selectedZoneId] = value;
        
        this._hass.callService('media_player', 'volume_set', {
          entity_id: this.selectedZoneId,
          volume_level: value / 100
        });
      } else if (ev.target.classList.contains('linked-vol-slider')) {
        const targetZoneId = ev.target.getAttribute('data-zone');
        const value = parseInt(ev.target.value);
        this._optimisticVolumes[targetZoneId] = value;
        
        this._hass.callService('media_player', 'volume_set', {
          entity_id: targetZoneId,
          volume_level: value / 100
        });
      } else if (ev.target.id === 'eq-preset-select') {
        const channel = this.getChannel(this.selectedZoneId);
        const eqPresetEntity = channel ? this.findEntityByUniqueId(`_ch${channel}_eq_preset`) : null;
        
        if (eqPresetEntity) {
          this._hass.callService('select', 'select_option', {
            entity_id: eqPresetEntity,
            option: ev.target.value
          });
        }
      } else if (ev.target.id === 'bass-slider') {
        const channel = this.getChannel(this.selectedZoneId);
        const bassEntity = channel ? this.findEntityByUniqueId(`_ch${channel}_bass`) : null;
        
        if (bassEntity) {
          this._hass.callService('number', 'set_value', {
            entity_id: bassEntity,
            value: parseFloat(ev.target.value)
          });
        }
      } else if (ev.target.id === 'treble-slider') {
        const channel = this.getChannel(this.selectedZoneId);
        const trebleEntity = channel ? this.findEntityByUniqueId(`_ch${channel}_treble`) : null;
        
        if (trebleEntity) {
          this._hass.callService('number', 'set_value', {
            entity_id: trebleEntity,
            value: parseFloat(ev.target.value)
          });
        }
      }
    });
    
    this.addEventListener('input', (ev) => {
      if (ev.target.id === 'volume-slider') {
        const volText = this.querySelector('#vol-text');
        if (volText) volText.textContent = `${ev.target.value}%`;
      } else if (ev.target.classList.contains('linked-vol-slider')) {
        const span = ev.target.nextElementSibling;
        if (span) span.textContent = `${ev.target.value}%`;
      } else if (ev.target.id === 'bass-slider') {
        const text = this.querySelector('#bass-text');
        const val = ev.target.value;
        if (text) text.textContent = `${val > 0 ? '+' : ''}${val}`;
      } else if (ev.target.id === 'treble-slider') {
        const text = this.querySelector('#treble-text');
        const val = ev.target.value;
        if (text) text.textContent = `${val > 0 ? '+' : ''}${val}`;
      }
    });
    
    this.addEventListener('click', (ev) => {
      // Mark as user interacting
      this._userInteracting = true;
      if (this._interactTimeout) clearTimeout(this._interactTimeout);
      this._interactTimeout = setTimeout(() => { this._userInteracting = false; }, 10000);
      
      // Power Button
      if (ev.target.closest('#power-btn')) {
        this._hass.callService('media_player', 'toggle', {
          entity_id: this.selectedZoneId
        });
      }
      
      // Mute Button
      if (ev.target.closest('#mute-btn')) {
        const selectedZoneState = this._hass.states[this.selectedZoneId];
        const isMuted = this._optimisticMutes[this.selectedZoneId] !== undefined ? this._optimisticMutes[this.selectedZoneId] : selectedZoneState?.attributes?.is_volume_muted || false;
        
        this._optimisticMutes[this.selectedZoneId] = !isMuted;
        
        // Optimistically toggle icon
        const icon = ev.target.closest('#mute-btn').querySelector('ha-icon');
        if (icon) {
          icon.setAttribute('icon', !isMuted ? 'mdi:volume-off' : 'mdi:volume-high');
        }
        
        this._hass.callService('media_player', 'volume_mute', {
          entity_id: this.selectedZoneId,
          is_volume_muted: !isMuted
        });
      }
      
      // Linked Mute Buttons
      const linkedMute = ev.target.closest('.linked-mute-btn');
      if (linkedMute) {
        const targetZoneId = linkedMute.getAttribute('data-zone');
        const zoneState = this._hass.states[targetZoneId];
        const isMuted = this._optimisticMutes[targetZoneId] !== undefined ? this._optimisticMutes[targetZoneId] : zoneState?.attributes?.is_volume_muted || false;
        
        this._optimisticMutes[targetZoneId] = !isMuted;
        
        // Optimistically toggle icon
        const icon = linkedMute.querySelector('ha-icon');
        if (icon) {
          icon.setAttribute('icon', !isMuted ? 'mdi:volume-off' : 'mdi:volume-high');
        }
        
        this._hass.callService('media_player', 'volume_mute', {
          entity_id: targetZoneId,
          is_volume_muted: !isMuted
        });
      }
      
      // Favorite Button
      if (ev.target.closest('#fav-btn')) {
        this.saveFavorite();
      }
      
      // Browse Media Button
      if (ev.target.closest('#browse-btn')) {
        const mappedPlayerId = this._config?.mappings?.[this.selectedInputName];
        if (mappedPlayerId) {
          const event = new CustomEvent('hass-more-info', {
            detail: { entityId: mappedPlayerId },
            bubbles: true,
            composed: true
          });
          this.dispatchEvent(event);
        }
      }
      
      
      // Toggle Manual Favorite Form
      if (ev.target.closest('#toggle-manual-fav')) {
        const form = this.querySelector('#manual-fav-form');
        if (form) {
          form.style.display = form.style.display === 'none' ? 'flex' : 'none';
        }
      }
      
      // Save Manual Favorite
      if (ev.target.closest('#save-manual-fav')) {
        const nameInput = this.querySelector('#manual-fav-name');
        const inputSelect = this.querySelector('#manual-fav-input');
        const cmdInput = this.querySelector('#manual-fav-cmd');
        
        if (nameInput && inputSelect && cmdInput && nameInput.value && cmdInput.value) {
          const favorites = [...(this._config.favorites || JSON.parse(localStorage.getItem('control4_favorites') || '[]'))];
          
          const selectedInput = inputSelect.value;
          const mappedPlayerId = this._config?.mappings?.[selectedInput];
          
          // Check for duplicates (by name or command)
          const exists = favorites.some(f => f.name === nameInput.value || f.media_title === cmdInput.value);
          
          if (!exists) {
            favorites.push({
              name: nameInput.value,
              zone: this.selectedZoneId, // Use current zone
              input: selectedInput,      // Use selected input
              player: mappedPlayerId,    // Use mapped player for that input
              media_title: cmdInput.value
            });
            
            this._config.favorites = favorites;
            localStorage.setItem('control4_favorites', JSON.stringify(favorites));
            
            // Clear form
            nameInput.value = '';
            cmdInput.value = '';
            this.querySelector('#manual-fav-form').style.display = 'none';
            
            this.render(true);
          }
        }
      }
      
      // Zone Joining (Click on Zone Chip)
      const zoneChip = ev.target.closest('.zone-chip');
      if (zoneChip) {
        const targetZoneId = zoneChip.getAttribute('data-zone');
        const isJoined = zoneChip.classList.contains('joined');
        
        const zoneState = this._hass.states[targetZoneId];
        const inputs = zoneState?.attributes?.source_list || [];
        
        if (isJoined) {
          // Unjoin: Set to configurable default input or fallback to first input
          let defaultInput = this._config.unjoin_default_input;
          if (!defaultInput || !inputs.includes(defaultInput)) {
            defaultInput = inputs.length > 0 ? inputs[0] : 'None';
          }
          
          this._optimisticSources[targetZoneId] = defaultInput;
          
          this._hass.callService('media_player', 'select_source', {
            entity_id: targetZoneId,
            source: defaultInput
          });
        } else {
          // Join: Set target zone to the SAME source as current zone
          this._optimisticSources[targetZoneId] = this.selectedInputName;
          
          this._hass.callService('media_player', 'select_source', {
            entity_id: targetZoneId,
            source: this.selectedInputName
          });
        }
        
        this.render(true);
      }
      
      // Source Player Controls
      if (ev.target.closest('#prev-btn')) {
        const mappedPlayerId = this._config?.mappings?.[this.selectedInputName];
        if (mappedPlayerId) this._hass.callService('media_player', 'media_previous_track', { entity_id: mappedPlayerId });
      }
      if (ev.target.closest('#play-btn')) {
        const mappedPlayerId = this._config?.mappings?.[this.selectedInputName];
        if (mappedPlayerId) {
          const playerState = this._hass.states[mappedPlayerId];
          const service = playerState.state === 'playing' ? 'media_pause' : 'media_play';
          this._hass.callService('media_player', service, { entity_id: mappedPlayerId });
        }
      }
      if (ev.target.closest('#next-btn')) {
        const mappedPlayerId = this._config?.mappings?.[this.selectedInputName];
        if (mappedPlayerId) this._hass.callService('media_player', 'media_next_track', { entity_id: mappedPlayerId });
      }
      
      // Favorite Chips
      const chip = ev.target.closest('.fav-chip');
      if (chip) {
        const index = parseInt(chip.getAttribute('data-index'));
        const favorites = this._config.favorites || JSON.parse(localStorage.getItem('control4_favorites') || '[]');
        
        // If clicked delete
        if (ev.target.tagName === 'HA-ICON' && ev.target.getAttribute('data-action') === 'delete') {
          favorites.splice(index, 1);
          this._config.favorites = favorites;
          localStorage.setItem('control4_favorites', JSON.stringify(favorites));
          this.render(true);
          ev.stopPropagation();
          return;
        }
        
        // Recall favorite
        const fav = favorites[index];
        if (fav) {
          this.selectedZoneId = fav.zone;
          this.selectedInputName = fav.input;
          this.render(true);
          
          // 1. Switch source on the amp
          this._hass.callService('media_player', 'select_source', {
            entity_id: fav.zone,
            source: fav.input
          });
          
          // 2. Tell the source player to play BY TITLE
          if (fav.player && fav.media_title) {
            setTimeout(() => {
              const cmd = fav.media_title.startsWith('play ') ? fav.media_title : `play ${fav.media_title}`;
              
              this._hass.callService('media_player', 'play_media', {
                entity_id: fav.player,
                media_content_id: cmd,
                media_content_type: 'custom'
              });
            }, 1000); // Give the amp a second to switch
          }
        }
      }
    });
  }
  
  saveFavorite() {
    const mappedPlayerId = this._config?.mappings?.[this.selectedInputName];
    const mappedPlayerState = mappedPlayerId ? this._hass.states[mappedPlayerId] : null;
    
    const favorites = [...(this._config.favorites || JSON.parse(localStorage.getItem('control4_favorites') || '[]'))];
    let name = this.selectedInputName;
    let media_title = null;
    
    if (mappedPlayerState) {
      const trackTitle = mappedPlayerState.attributes.media_title;
      const artist = mappedPlayerState.attributes.media_artist;
      if (trackTitle) {
        name = artist ? `${trackTitle} - ${artist}` : trackTitle;
        media_title = trackTitle; // Save just the title for searching
      }
    }
    
    const newFav = {
      name: name,
      zone: this.selectedZoneId,
      input: this.selectedInputName,
      player: mappedPlayerId,
      media_title: media_title // Store the track title explicitly
    };
    
    // Check for duplicates before adding auto-favorite
    const exists = favorites.some(f => f.media_title === media_title && f.input === this.selectedInputName);
    
    if (!exists && media_title) {
      favorites.push(newFav);
      this._config.favorites = favorites;
      localStorage.setItem('control4_favorites', JSON.stringify(favorites));
      this.render(true); // Force re-render to show new chip
    }
  }
  
  updateVolatileStates() {
    const selectedZoneState = this._hass.states[this.selectedZoneId];
    if (!selectedZoneState) return;
    
    // Helper to get volume (including optimistic)
    const getZoneVol = (id) => this._optimisticVolumes[id] !== undefined ? this._optimisticVolumes[id] : Math.round((this._hass.states[id]?.attributes?.volume_level || 0) * 100);
    
    const vol = getZoneVol(this.selectedZoneId);
    
    // Helper to get mute state (including optimistic)
    const getZoneMute = (id) => this._optimisticMutes[id] !== undefined ? this._optimisticMutes[id] : this._hass.states[id]?.attributes?.is_volume_muted || false;
    
    const isMuted = getZoneMute(this.selectedZoneId);
    const isOn = selectedZoneState.state === 'on' || selectedZoneState.state === 'playing';
    
    const volSlider = this.querySelector('#volume-slider');
    const volText = this.querySelector('#vol-text');
    const muteBtn = this.querySelector('#mute-btn');
    const powerBtn = this.querySelector('#power-btn');
    
    if (volSlider && document.activeElement !== volSlider) {
      volSlider.value = vol;
      if (volText) volText.textContent = `${vol}%`;
    }
    
    if (muteBtn) {
      const icon = muteBtn.querySelector('ha-icon');
      if (icon) icon.setAttribute('icon', isMuted ? 'mdi:volume-off' : 'mdi:volume-high');
    }
    
    if (powerBtn) {
      powerBtn.style.color = isOn ? '#03a9f4' : 'var(--text-color-disabled)';
    }
    
    // Update media info dynamically
    const mappedPlayerId = this._config?.mappings?.[this.selectedInputName];
    const mediaContainer = this.querySelector('#media-info-container');
    const cardBg = this.querySelector('.card-bg');
    const cardEl = this.querySelector('.glass-card');
    
    if (mediaContainer && mappedPlayerId && this._hass.states[mappedPlayerId]) {
      const playerState = this._hass.states[mappedPlayerId];
      const title = playerState.attributes.media_title || 'Unknown Title';
      const artist = playerState.attributes.media_artist || 'Unknown Artist';
      const artwork = playerState.attributes.entity_picture;
      
      const titleEl = mediaContainer.querySelector('.media-title');
      const artistEl = mediaContainer.querySelector('.media-artist');
      const artEl = mediaContainer.querySelector('.media-artwork');
      const playBtn = mediaContainer.querySelector('#play-btn ha-icon');
      
      if (titleEl) titleEl.textContent = title;
      if (artistEl) artistEl.textContent = artist;
      
      if (artEl) {
        if (artwork) {
          artEl.innerHTML = `<img src="${artwork}" style="width: 70px; height: 70px; border-radius: 8px; object-fit: cover; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">`;
          if (cardBg) {
            cardBg.style.backgroundImage = `url('${artwork}')`;
            cardBg.style.display = 'block';
          }
          if (cardEl) cardEl.classList.add('has-artwork');
        } else {
          artEl.innerHTML = `
            <div style="width: 70px; height: 70px; border-radius: 8px; background: var(--glass-bg); display: flex; align-items: center; justify-content: center;">
              <ha-icon icon="mdi:music" style="color: var(--text-color-disabled); font-size: 30px;"></ha-icon>
            </div>
          `;
          if (cardBg) cardBg.style.display = 'none';
          if (cardEl) cardEl.classList.remove('has-artwork');
        }
      }
      
      if (playBtn) {
        playBtn.setAttribute('icon', playerState.state === 'playing' ? 'mdi:pause' : 'mdi:play');
      }
    } else {
      if (cardEl) cardEl.classList.remove('has-artwork');
      if (cardBg) cardBg.style.display = 'none';
    }
    
    // Update zone joining states dynamically
    const zoneChips = this.querySelectorAll('.zone-chip');
    zoneChips.forEach(chip => {
      const targetZoneId = chip.getAttribute('data-zone');
      const zoneState = this._hass.states[targetZoneId];
      const source = this._optimisticSources[targetZoneId] || zoneState?.attributes?.source;
      const isJoined = source === this.selectedInputName;
      
      if (isJoined) {
        chip.classList.add('joined');
      } else {
        chip.classList.remove('joined');
      }
    });
    
    // Update linked volumes dynamically
    const linkedSliders = this.querySelectorAll('.linked-vol-slider');
    linkedSliders.forEach(slider => {
      const targetZoneId = slider.getAttribute('data-zone');
      const zMuted = getZoneMute(targetZoneId);
      const zVol = getZoneVol(targetZoneId);
      
      const container = slider.closest('.vol-container');
      if (container) {
        const icon = container.querySelector('button ha-icon');
        if (icon) icon.setAttribute('icon', zMuted ? 'mdi:volume-off' : 'mdi:volume-high');
      }
      
      if (document.activeElement !== slider) {
        slider.value = zVol;
        const span = slider.nextElementSibling;
        if (span) span.textContent = `${zVol}%`;
      }
    });
    
  }
}

// GUI Editor Class
class Control4CardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config || {};
  }

  set hass(hass) {
    this._hass = hass;
    
    if (!this._entityReg && !this._fetchingReg && hass && typeof hass.callWS === 'function') {
      this._fetchingReg = true;
      hass.callWS({ type: 'config/entity_registry/list' }).then(r => {
        this._entityReg = r;
        this._fetchingReg = false;
        this.render(true);
      }).catch(e => {
        this._entityReg = [];
        this._fetchingReg = false;
      });
    }
    
    this.render();
  }

  render(force = false) {
    if (!this._hass) return;
    if (!this._config) return; // Wait for config
    
    // Avoid blowing away innerHTML on every hass update
    if (!force && this.querySelector('#editor-zone-select')) {
      return;
    }
    
    // Find zones for the dropdown
    let zones = [];
    if (this._entityReg) {
      const integrationEntities = this._entityReg.filter(e => e.platform === 'control4_mediaplayer');
      zones = integrationEntities
        .filter(e => e.entity_id.startsWith('media_player.'))
        .map(e => e.entity_id)
        .filter(id => id in this._hass.states);
    }
    
    if (zones.length === 0) {
      const refZone = this._config.default_zone || Object.keys(this._hass.states).find(id => id.startsWith('media_player.') && this._hass.states[id].attributes.source_list);
      const refSourceList = refZone ? this._hass.states[refZone].attributes.source_list : [];
      zones = Object.keys(this._hass.states).filter(id => {
        if (!id.startsWith('media_player.')) return false;
        const state = this._hass.states[id];
        return state && JSON.stringify(state.attributes.source_list || []) === JSON.stringify(refSourceList);
      });
    }
    const selectedZone = this._config.default_zone || (zones.length > 0 ? zones[0] : '');
    
    let inputs = [];
    if (selectedZone && this._hass.states[selectedZone]) {
      inputs = this._hass.states[selectedZone].attributes.source_list || [];
    }
    
    const mappings = this._config.mappings || {};
    const allPlayers = Object.keys(this._hass.states).filter(id => id.startsWith('media_player.') && !zones.includes(id));

    this.innerHTML = `
      <div style="padding: 16px; color: var(--primary-text-color, white); background: var(--ha-card-background, var(--card-background-color, #1c1c1c)); border: 1px solid var(--ha-card-border-color, var(--divider-color, #444)); border-radius: 8px;">
        <h3 style="margin-top: 0; margin-bottom: 16px;">Control4 Card Configuration</h3>
        
        <div style="margin-bottom: 16px;">
          <label style="display: block; margin-bottom: 4px; font-size: 12px; color: var(--secondary-text-color, #aaa);">Card Title</label>
          <input id="editor-title" type="text" value="${this._config.title || 'Control4 Command Center'}" style="width: 100%; padding: 8px; background: var(--card-background-color, #2c2c2c); color: var(--primary-text-color, white); border: 1px solid var(--ha-card-border-color, var(--divider-color, #444)); border-radius: 4px; box-sizing: border-box;">
        </div>

        <div style="margin-bottom: 16px;">
          <label style="display: block; margin-bottom: 4px; font-size: 12px; color: var(--secondary-text-color, #aaa);">Default Zone</label>
          <select id="editor-zone-select" style="width: 100%; padding: 8px; background: var(--card-background-color, #2c2c2c); color: var(--primary-text-color, white); border: 1px solid var(--ha-card-border-color, var(--divider-color, #444)); border-radius: 4px; box-sizing: border-box;">
            ${zones.map(id => `<option value="${id}" ${id === selectedZone ? 'selected' : ''}>${this._hass.states[id].attributes.friendly_name || id}</option>`).join('')}
          </select>
        </div>
        
        <div style="margin-bottom: 16px;">
          <label style="display: block; margin-bottom: 4px; font-size: 12px; color: var(--secondary-text-color, #aaa);">Unjoin Default Input</label>
          <select id="editor-unjoin-input" style="width: 100%; padding: 8px; background: var(--card-background-color, #2c2c2c); color: var(--primary-text-color, white); border: 1px solid var(--ha-card-border-color, var(--divider-color, #444)); border-radius: 4px; box-sizing: border-box;">
            <option value="None" ${this._config.unjoin_default_input === 'None' ? 'selected' : ''}>None</option>
            ${inputs.map(input => `<option value="${input}" ${this._config.unjoin_default_input === input ? 'selected' : ''}>${input}</option>`).join('')}
          </select>
        </div>

        <div style="margin-bottom: 16px;">
          <label style="display: block; margin-bottom: 8px; font-size: 12px; color: var(--secondary-text-color, #aaa);">Input Mappings</label>
          ${inputs.map(input => `
            <div style="display: flex; align-items: center; margin-bottom: 8px;">
              <div style="flex: 1; font-size: 14px;">${input}</div>
              <div style="flex: 2;">
                <select class="player-select" data-input="${input}" style="width: 100%; padding: 6px; background: var(--card-background-color, #2c2c2c); color: var(--primary-text-color, white); border: 1px solid var(--ha-card-border-color, var(--divider-color, #444)); border-radius: 4px; box-sizing: border-box;">
                  <option value="">None</option>
                  ${allPlayers.map(id => `<option value="${id}" ${mappings[input] === id ? 'selected' : ''}>${this._hass.states[id].attributes.friendly_name || id}</option>`).join('')}
                </select>
              </div>
            </div>
          `).join('')}
        </div>
        
        <button id="save-btn" style="width: 100%; padding: 10px; background: var(--primary-color, #03a9f4); color: white; border: none; border-radius: 4px; font-weight: bold; cursor: pointer;">Save Configuration</button>
      </div>
    `;
    
    // Bind events
    const zoneSelect = this.querySelector('#editor-zone-select');
    if (zoneSelect) {
      zoneSelect.addEventListener('change', (ev) => {
        const newConfig = { ...this._config, default_zone: ev.target.value };
        this._config.default_zone = ev.target.value; // Update local config too
        this.render(true); // Force re-render to update inputs
        this.dispatchEvent(new CustomEvent('config-changed', {
          detail: { config: newConfig },
          bubbles: true,
          composed: true
        }));
      });
    }
    
    const saveBtn = this.querySelector('#save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => {
        const newConfig = { ...this._config };
        newConfig.mappings = {};
        
        newConfig.title = this.querySelector('#editor-title').value;
        newConfig.unjoin_default_input = this.querySelector('#editor-unjoin-input').value;
        newConfig.default_zone = this.querySelector('#editor-zone-select').value;
        
        this.querySelectorAll('.player-select').forEach(select => {
          const input = select.getAttribute('data-input');
          const value = select.value;
          if (value) {
            newConfig.mappings[input] = value;
          }
        });
        
        this.dispatchEvent(new CustomEvent('config-changed', {
          detail: { config: newConfig },
          bubbles: true,
          composed: true
        }));
      });
    }
  }
}

customElements.define('control4-card-editor', Control4CardEditor);
customElements.define('control4-mediaplayer-card', Control4Card);

// Register card in the card picker
window.customCards = window.customCards || [];
const cardExists = window.customCards.some(c => c.type === "control4-mediaplayer-card");
if (!cardExists) {
  window.customCards.push({
    type: "control4-mediaplayer-card",
    name: "Control4 Media Player Card",
    preview: false,
    description: "A custom card to control Control4 media zones."
  });
}
