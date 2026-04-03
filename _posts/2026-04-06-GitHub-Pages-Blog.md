---
layout: post
title: "Building a Technical Blog on GitHub Pages for AWS Community Builders"
date: 2026-04-06
categories: community writing github
tags: github-pages jekyll blogging community-builders writing technical-writing
---

# Building a Technical Blog on GitHub Pages for AWS Community Builders

This blog has been running on GitHub Pages for over three years now. It's free, requires zero infrastructure management (ironic for an infrastructure blog), and gets out of the way so I can focus on writing. If you're an AWS Community Builder — or thinking about becoming one — having a place to share what you're learning is one of the most valuable things you can do. Here's how I set this up and what I've learned about maintaining a writing habit.

## Why GitHub Pages

- Free hosting, free SSL, free CDN
- Markdown-based — write in the same format you use for READMEs
- Version controlled — your blog posts are just git commits
- No database, no server, no patching
- Custom domain support if you want it
- Jekyll builds automatically on push

For a technical blog, this is hard to beat. You don't need WordPress, you don't need a CMS, you don't need to manage anything.

## The Setup (15 Minutes)

### 1. Create the Repository

Create a repo named `yourusername.github.io`. That's it — GitHub automatically serves it as a website.

### 2. Pick a Theme

GitHub Pages supports several themes out of the box. I use the Minimal theme via `remote_theme`:

```yaml
# _config.yml
author: 'your-name'
title: 'Your Blog Title'
description: 'A short description of your blog'

remote_theme: pages-themes/minimal@v0.2.0
plugins:
  - jekyll-remote-theme
```

### 3. Create Your First Post

Posts go in the `_posts` directory with the naming convention `YYYY-MM-DD-title.md`:

```markdown
---
layout: post
title: "My First Post"
date: 2026-04-06
categories: aws
tags: aws getting-started
---

# Hello World

This is my first post about building on AWS.
```

### 4. Push and You're Live

```bash
git add .
git commit -m "Initial blog setup"
git push origin main
```

Your blog is now live at `https://yourusername.github.io`.

## Project Structure

Here's what a mature blog looks like:

```
your-blog/
├── _config.yml          # Site configuration
├── _layouts/
│   ├── default.html     # Base layout
│   └── post.html        # Post layout
├── _posts/
│   ├── 2026-01-01-first-post.md
│   └── 2026-02-01-second-post.md
├── _includes/
│   └── head-custom.html # Custom head elements
├── assets/
│   ├── css/
│   ├── images/
│   └── js/
├── about.md             # About page
├── README.md            # Homepage (post listing)
└── 404.html
```

## Writing Workflow

My workflow is simple:

1. Create a new file in `_posts/` with today's date
2. Write in VS Code with markdown preview
3. Commit and push
4. GitHub Actions builds and deploys automatically

I keep a template file for consistency:

```markdown
---
layout: post
title: "template"
date: 2000-01-01 00:00:00 -0000
categories:
---

# Overview
```

## The Post Template I Actually Use

After writing 30+ posts, I've settled on a structure:

```markdown
---
layout: post
title: "Descriptive Title That Includes the AWS Service Name"
date: YYYY-MM-DD
categories: aws [primary-category] [secondary-category]
tags: aws [specific-service] [topic] [related-concepts]
---

# Title (can be different from front matter title)

Opening paragraph: What problem does this solve? Why should someone care?
Keep it to 2-3 sentences.

## What/Why Section

Brief context. What is this service/tool/pattern? Why use it?

## Implementation / How-To

The meat of the post. Code examples, CLI commands, step-by-step instructions.

## Best Practices / Tips

What I learned the hard way so you don't have to.

## Conclusion (optional)

Keep it short. Summarize the key takeaway.

---

**References:**
- [Link to official docs]
- [Link to related resources]
```

## Maintaining a Monthly Cadence

The AWS Community Builder program benefits from consistent content creation. Here's what's worked for me:

### Write About What You're Already Doing

The biggest mistake is trying to invent topics. Instead:
- Solved a tricky problem at work? Write about it.
- Set up a new AWS service? Document the process.
- Found a gap in the official docs? Fill it.
- Attended re:Invent? Write a recap.

Every month I'm working on something AWS-related. The blog post is just the documentation I'd write anyway, formatted for a broader audience.

### Keep a Running List

I maintain a simple text file of potential topics. When I hit something interesting during my day job, I add it to the list. When it's time to write, I pick from the list instead of staring at a blank page.

### Set a Deadline, Not a Word Count

I publish on the first Monday of each month. The post is as long as it needs to be — some are 500 words, some are 2,000. Consistency matters more than length.

### Don't Aim for Perfection

A published post that's 80% polished is infinitely more valuable than a perfect post that's still in drafts. Ship it, and you can always update it later (it's git, after all).

## SEO and Discovery (Minimal Effort)

I don't obsess over SEO, but a few basics help:

- Use descriptive titles that include the AWS service name
- Add categories and tags to front matter
- Write clear opening paragraphs (they become meta descriptions)
- Use headers (H2, H3) to structure content
- Include code blocks — they're what people are searching for

## Custom Domain (Optional)

If you want a custom domain:

1. Buy a domain
2. Add a `CNAME` file to your repo with your domain name
3. Configure DNS:
   ```
   CNAME  www  yourusername.github.io
   A      @    185.199.108.153
   A      @    185.199.109.153
   A      @    185.199.110.153
   A      @    185.199.111.153
   ```
4. Enable HTTPS in the repo settings

## What I'd Do Differently

Looking back over three years of blogging:

- I'd have started sooner — the first post is the hardest, and it doesn't need to be good
- I'd have been more consistent in the early months (there are some gaps)
- I'd have added more diagrams — architecture diagrams make posts much more accessible
- I wouldn't have worried about analytics — write for the practice, not the pageviews

## For Community Builder Applicants

If you're applying to the AWS Community Builder program, a blog with a few solid posts demonstrates:

- You're actively building on AWS
- You can communicate technical concepts clearly
- You're contributing to the community
- You have a consistent track record

You don't need dozens of posts. Five or six well-written articles about real problems you've solved is more than enough.

## The Meta Conclusion

This post is the 36th on this blog. Some months the writing flows easily, other months it's a grind. But every post has taught me something — either about the topic itself or about how to explain technical concepts more clearly. That alone makes it worth it.

If you're on the fence about starting a technical blog, just do it. Create the repo, write the first post, push it. You can figure out the rest as you go.

---

**References:**
- [GitHub Pages Documentation](https://docs.github.com/en/pages)
- [Jekyll Documentation](https://jekyllrb.com/docs/)
- [AWS Community Builders](https://aws.amazon.com/developer/community/community-builders/)
