from datetime import datetime
from app.auth.models import BlogPost, Comment, Document
from . import board_bp
from flask_login import current_user, login_required
import os
from flask import (
    Blueprint, flash, render_template, current_app, request, send_from_directory,
    abort, redirect, url_for
)
from sqlalchemy.orm import joinedload

from app.extensions import db

@board_bp.route('/')
@login_required
def dashboard():
    return "Board Member Dashboard"






@board_bp.route('/financial-reports')
@login_required
def financial_reports():
    return render_template('board/financial_reports.html')

@board_bp.route('/performance-metrics')
@login_required
def performance_metrics():
    return render_template('board/performance_metrics.html')

@board_bp.route('/strategic-planning')
@login_required
def strategic_planning():
    return render_template('board/strategic_planning.html')

@board_bp.route('/governance')
@login_required
def governance():
    return render_template('board/governance.html')

@board_bp.route('/resources')
@login_required
def resources():
    dept_id = current_user.department_id
    
    # Fetch blog posts with comments count
    blog_posts = (
        BlogPost.query
        .filter_by(department_id=dept_id, status='published')
        .options(db.joinedload(BlogPost.author))
        .options(db.joinedload(BlogPost.comments))
        .order_by(BlogPost.created_at.desc())
        .all()
    )
    
    # Fetch documents with comments count
    documents = (
        Document.query
        .filter_by(department_id=dept_id)
        .options(db.joinedload(Document.uploader))
        .options(db.joinedload(Document.comments))
        .order_by(Document.created_at.desc())
        .all()
    )
    
    return render_template(
        'view_resources.html',
        blog_posts=blog_posts,
        documents=documents
    )

@board_bp.route('/add-comment', methods=['POST'])
@login_required
def add_comment():
    resource_type = request.form['resource_type']
    resource_id = request.form['resource_id']
    content = request.form['content']
    
    new_comment = Comment(
        content=content,
        user_id=current_user.id,
        created_at=datetime.utcnow()
    )
    
    if resource_type == 'blog':
        new_comment.blog_post_id = resource_id
    elif resource_type == 'document':
        new_comment.document_id = resource_id
    
    db.session.add(new_comment)
    db.session.commit()
    
    flash('Comment added successfully!', 'success')
    return redirect(request.referrer)

@board_bp.route('/blog/<int:blog_id>', methods=['GET', 'POST'])
@login_required
def view_blog(blog_id):
    """
    Show a single published blog post with comments, 
    only if it belongs to the current_user's department.
    Also handles new comment submissions via POST.
    """
    # Load post with all related data
    post = BlogPost.query.options(
        db.joinedload(BlogPost.author),
        db.joinedload(BlogPost.department),
        db.joinedload(BlogPost.comments).joinedload(Comment.user)
    ).get_or_404(blog_id)

    # Permission check
    if post.department_id != current_user.department_id or post.status != 'published':
        abort(404)

    # Handle comment form submission
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if not content:
            flash('Comment cannot be empty.', 'error')
        else:
            new_comment = Comment(
                content=content,
                user_id=current_user.id,
                blog_post_id=post.id,
                created_at=datetime.utcnow()
            )
            db.session.add(new_comment)
            db.session.commit()
            flash('Your comment has been posted!', 'success')
        return redirect(url_for('board.view_blog', blog_id=blog_id))

    # Get related posts from the same department
    related_posts = BlogPost.query.filter(
        BlogPost.department_id == current_user.department_id,
        BlogPost.status == 'published',
        BlogPost.id != post.id
    ).order_by(db.func.random()).limit(3).all()

    return render_template(
        'blog.html',
        post=post,
        related_posts=related_posts
    )

@board_bp.route('/delete-comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    """Delete a comment with full security and auditing"""

    
    # Get comment with associated blog post
    comment = Comment.query.options(
        db.joinedload(Comment.blog_post)
    ).get_or_404(comment_id)
    
    # Permission check
    if comment.user_id != current_user.id and not current_user.is_admin():
        abort(403, description="You don't have permission to delete this comment")
    
    # Get blog ID before deletion
    blog_id = comment.blog_post_id
    

    db.session.delete(comment)
    db.session.commit()
    
    flash('Comment deleted successfully', 'success')
    return redirect(url_for('board.view_blog', blog_id=blog_id))

@board_bp.route('/download-resource-document/<int:document_id>', methods=['GET'])
def download_resource_document(document_id):
    """
    Serve a document file for download, only if it belongs to
    the current_user’s department.
    """
    doc = Document.query.get_or_404(document_id)

    # Enforce department-level access
    if doc.department_id != current_user.department_id:
        abort(404)

    upload_folder = current_app.config['UPLOAD_FOLDER']
    full_path = os.path.join(upload_folder, doc.file_path)
    if not os.path.isfile(full_path):
        abort(404)

    return send_from_directory(
        directory=upload_folder,
        path=doc.file_path,
        as_attachment=True,
        download_name=doc.title + os.path.splitext(doc.file_path)[1]
    )