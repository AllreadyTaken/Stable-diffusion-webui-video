import numpy as np
from tqdm import trange
import glob
import os
import modules.scripts as scripts
import gradio as gr
import subprocess
from modules import processing, shared, sd_samplers, images
from modules.processing import Processed
from modules.sd_samplers import samplers
from modules.shared import opts, cmd_opts, state

class Script(scripts.Script):
    def title(self):
        return "Videos"

    def show(self, is_img2img):
        return is_img2img

    def ui(self, is_img2img):
        prompt_end = gr.Textbox(label='Prompt end', value="")
        seconds = gr.Slider(minimum=1, maximum=250, step=1, label='Seconds', value=4)
        fps = gr.Slider(minimum=10, maximum=60, step=1, label='FPS', value=30)
        denoising_strength_change_factor = gr.Slider(minimum=0.9, maximum=1.1, step=0.01,
                                                     label='Denoising strength change factor', value=1)
        return [prompt_end, seconds, fps, denoising_strength_change_factor]  # , denoising_strength_change_factor

    def run(self, p, prompt_end, seconds, fps, denoising_strength_change_factor):  # , denoising_strength_change_factor
        processing.fix_seed(p)

        p.batch_size = 1
        p.n_iter = 1

        batch_count = p.n_iter
        p.extra_generation_params = {
            "Denoising strength change factor": denoising_strength_change_factor,
        }

        output_images, info = None, None
        initial_seed = None
        initial_info = None

        loops = seconds * fps

        grids = []
        all_images = []
        state.job_count = loops * batch_count

        # fifty = int(loops/2)

        if opts.img2img_color_correction:
            p.color_corrections = [processing.setup_color_correction(p.init_images[0])]

        for n in range(batch_count):
            history = []

            for i in range(loops):
                p.n_iter = 1
                p.batch_size = 1
                p.do_not_save_grid = True

                if i > 0 and prompt_end not in p.prompt and prompt_end != '':
                    p.prompt = prompt_end + ' ' + p.prompt

                state.job = f"Iteration {i + 1}/{loops}, batch {n + 1}/{batch_count}"

                processed = processing.process_images(p)

                if initial_seed is None:
                    initial_seed = processed.seed
                    initial_info = processed.info

                init_img = processed.images[0]

                p.init_images = [init_img]
                p.seed = processed.seed + 1
                p.denoising_strength = min(max(p.denoising_strength * denoising_strength_change_factor, 0.1), 1)
                history.append(processed.images[0])

            grid = images.image_grid(history, rows=1)
            if opts.grid_save:
                images.save_image(grid, p.outpath_grids, "grid", initial_seed, p.prompt, opts.grid_format, info=info, short_filename=not opts.grid_extended_filename, grid=True, p=p)

            grids.append(grid)
            all_images += history

        if opts.return_grid:
            all_images = grids + all_images

        processed = Processed(p, [], initial_seed, initial_info)  # processed.images[0]

        files = [i for i in glob.glob(f'{p.outpath_samples}/*.png')]
        files.sort(key=lambda f: os.path.getmtime(f))
        files = files[-loops:]

        make_video_ffmpeg(o='outputs/video.mp4', files=files, fps=fps)
        processed.info = processed.info + '\nvideo save in stable-diffusion-webui\\outputs\\video.mp4'

        return processed


def install_ffmpeg(path):
    from basicsr.utils.download_util import load_file_from_url
    from zipfile import ZipFile

    ffmpeg_url = 'https://github.com/GyanD/codexffmpeg/releases/download/5.1.1/ffmpeg-5.1.1-full_build.zip'
    ffmpeg_dir = os.path.join(path, 'ffmpeg')

    ckpt_path = load_file_from_url(url=ffmpeg_url, model_dir=ffmpeg_dir)

    if not os.path.exists(os.path.abspath(os.path.join(ffmpeg_dir, 'ffmpeg.exe'))):
        with ZipFile(ckpt_path, 'r') as zipObj:
            listOfFileNames = zipObj.namelist()
            for fileName in listOfFileNames:
                if '/bin/' in fileName:
                    zipObj.extract(fileName, ffmpeg_dir)
        os.rename(os.path.join(ffmpeg_dir, listOfFileNames[0][:-1], 'bin', 'ffmpeg.exe'), os.path.join(ffmpeg_dir, 'ffmpeg.exe'))
        os.rename(os.path.join(ffmpeg_dir, listOfFileNames[0][:-1], 'bin', 'ffplay.exe'), os.path.join(ffmpeg_dir, 'ffplay.exe'))
        os.rename(os.path.join(ffmpeg_dir, listOfFileNames[0][:-1], 'bin', 'ffprobe.exe'), os.path.join(ffmpeg_dir, 'ffprobe.exe'))

        os.rmdir(os.path.join(ffmpeg_dir, listOfFileNames[0][:-1], 'bin'))
        os.rmdir(os.path.join(ffmpeg_dir, listOfFileNames[0][:-1]))
    return


def make_video_ffmpeg(o, files=[], fps=30):
    import modules
    path = modules.paths.script_path
    install_ffmpeg(path)

    str = '\n'.join(["file '" + os.path.join(path, f) + "'" for f in files])
    open('outputs/video.txt', 'w').write(str)

    subprocess.call(
        f'''ffmpeg/ffmpeg -r {fps} -f concat -safe 0 -i "outputs/video.txt" -vcodec libx264 -crf 10 -pix_fmt yuv420p {o} -y'''
    )
    subprocess.call(
        f'''ffmpeg/ffplay {o}'''
    )
    return o
