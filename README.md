

{% assign posts_by_year = site.posts | group_by_exp: "post", "post.date | date: '%Y'" %}
{% for year in posts_by_year %}
## {{ year.name }}

<ul>
{% for post in year.items %}<li>{{ post.date | date: "%b %-d" }} — <a href="{{ post.url }}">{{ post.title }}</a></li>
{% endfor %}</ul>

{% endfor %}
