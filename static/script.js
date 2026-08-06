document.addEventListener('DOMContentLoaded', () => {
    const generateBtn = document.getElementById('generate-btn');
    const scheduleBtn = document.getElementById('schedule-btn');
    const textInput = document.getElementById('text-input');
    const captionInput = document.getElementById('caption-input');
    const scheduledTimeInput = document.getElementById('scheduled-time');
    
    const statusPanel = document.getElementById('status-panel');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    
    const resultContainer = document.getElementById('result-container');
    const videoPlayer = document.getElementById('video-player');
    const errorMessage = document.getElementById('error-message');
    const scheduleSuccess = document.getElementById('schedule-success');
    
    let generatedFilename = null;
    let pollInterval = null;

    function showError(msg) {
        errorMessage.textContent = msg;
        errorMessage.classList.remove('hidden');
    }

    function hideError() {
        errorMessage.classList.add('hidden');
        errorMessage.textContent = '';
    }

    function updateProgress() {
        fetch('/progress')
            .then(res => res.json())
            .then(data => {
                progressBar.style.width = `${data.percent}%`;
                progressText.textContent = data.status;
            })
            .catch(err => console.error("Error fetching progress:", err));
    }

    generateBtn.addEventListener('click', async () => {
        const text = textInput.value.trim();
        const caption = captionInput.value;
        if (!text) {
            showError("Please enter some text!");
            return;
        }
        if (!caption) {
            showError("Please provide a caption before scheduling.");
            return;
        }

        hideError();
        scheduleSuccess.classList.add('hidden');
        resultContainer.classList.add('hidden');
        statusPanel.classList.remove('hidden');
        
        generateBtn.disabled = true;
        generateBtn.querySelector('.btn-text').textContent = "Generating...";
        generateBtn.querySelector('.loader').classList.remove('hidden');
        
        // Start polling progress
        pollInterval = setInterval(updateProgress, 500);

        try {
            const response = await fetch('/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: text,
                    aspect_ratio: '9:16'
                })
            });

            const data = await response.json();
            
            clearInterval(pollInterval);
            
            if (!response.ok || !data.success) {
                throw new Error(data.error || 'Generation failed');
            }

            // Success Generation
            progressBar.style.width = "100%";
            progressText.textContent = "Video Complete! Auto-Scheduling...";
            
            videoPlayer.src = data.video_url;
            generatedFilename = data.filename;
            
            resultContainer.classList.remove('hidden');

            // Auto-Schedule
            const scheduleResponse = await fetch('/schedule', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    filename: generatedFilename,
                    caption: caption
                })
            });

            const scheduleData = await scheduleResponse.json();
            
            if (!scheduleResponse.ok || !scheduleData.success) {
                throw new Error(scheduleData.error || 'Scheduling failed');
            }

            scheduleSuccess.classList.remove('hidden');
            progressText.textContent = "Scheduled Successfully!";
            
            // Reload page after a delay to show updated schedule
            setTimeout(() => {
                window.location.reload();
            }, 3000);

        } catch (err) {
            clearInterval(pollInterval);
            showError(err.message);
            statusPanel.classList.add('hidden');
        } finally {
            generateBtn.disabled = false;
            generateBtn.querySelector('.btn-text').textContent = "Generate & Auto-Schedule";
            generateBtn.querySelector('.loader').classList.add('hidden');
        }
    });
});

async function deletePost(id) {
    if (!confirm("Are you sure you want to cancel and delete this scheduled post?")) return;
    
    try {
        const response = await fetch(`/delete_schedule/${id}`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.success) {
            alert("Error: " + (data.error || "Failed to delete post"));
        } else {
            window.location.reload();
        }
    } catch (err) {
        alert("Error: " + err.message);
    }
}
