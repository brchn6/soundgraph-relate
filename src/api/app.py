# src/sgr/api/app.py
@app.route('/api/tracks/<track_id>/related')
@app.route('/api/users/<user_id>/similar') 
@app.route('/api/intersection')