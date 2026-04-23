const sqlite3 = require('sqlite3').verbose();
const path = require('path');

const DB_PATH = process.env.DB_PATH || path.join(__dirname, '..', 'data', 'video_kitchen.db');
const db = new sqlite3.Database(DB_PATH);

const recipes = [
  {
    id: 'social_teaser_w24',
    name: 'Social Media Teaser für W24',
    config: JSON.stringify({
      recipe: 'social_teaser_w24',
      target_duration: '20-30s',
      scene_count: '3-5',
      scene_selection: 'auto_highlights',
      music_mood: 'upbeat',
      music_bpm: '120-140',
      vo_style: 'punchy',
      aspect_ratio: '9:16',
      transitions: 'quick_cuts',
      captions: true
    })
  },
  {
    id: 'spicy_trailer',
    name: 'Spicy Trailer',
    config: JSON.stringify({
      recipe: 'spicy_trailer',
      target_duration: '30-45s',
      scene_count: '5-8',
      scene_selection: 'auto_highlights',
      music_mood: 'epic',
      music_bpm: '100-130',
      vo_style: 'dramatic',
      aspect_ratio: '16:9',
      transitions: 'crossfade',
      speed_ramps: true,
      impact_moments: true
    })
  },
  {
    id: 'highlight_abendsendung',
    name: 'Highlight Abendsendung',
    config: JSON.stringify({
      recipe: 'highlight_abendsendung',
      target_duration: '60-90s',
      scene_count: '6-12',
      scene_selection: 'auto_highlights',
      music_mood: 'professional',
      music_bpm: '90-110',
      vo_style: 'professional',
      aspect_ratio: '16:9',
      transitions: 'cut',
      lower_thirds: true
    })
  },
  {
    id: 'bts_soup',
    name: 'Behind the Scenes Soup',
    config: JSON.stringify({
      recipe: 'bts_soup',
      target_duration: '45-60s',
      scene_count: '5-8',
      scene_selection: 'random_diverse',
      music_mood: 'chill',
      music_bpm: '80-100',
      vo_style: 'conversational',
      aspect_ratio: '1:1',
      transitions: 'crossfade',
      filters: 'warm_vintage'
    })
  }
];

const insert = db.prepare('INSERT OR IGNORE INTO recipes (id, name, config) VALUES (?, ?, ?)');

for (const r of recipes) {
  insert.run(r.id, r.name, r.config);
}

insert.finalize();
console.log('Seeded', recipes.length, 'recipes');
db.close();
