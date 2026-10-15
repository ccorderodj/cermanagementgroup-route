import MiniCssExtractPlugin from 'mini-css-extract-plugin';
import { BuildOptions } from '../types/config';

// const cssLoader = {
//     test: /\.css$/i,
//     include: paths.tailwind,
//     use: ['style-loader', 'css-loader', 'postcss-loader'],
// }
// export function buildCssLoader(options: BuildOptions) {
//     const { isDev, paths } = options;
//     return {
//         test: /\.css$/i,
//         include: paths.tailwind,
//         use: ['style-loader', 'css-loader', 'postcss-loader'],
//         exclude: /node_modules/,
//     }
// }

export function buildCssLoader(options: BuildOptions) {
    const { isDev, paths } = options;
    return {
        test: /\.s[ac]ss$/i,
        exclude: /node_modules/,
        include: paths.tailwind,
        use: [
            isDev ? 'style-loader' : MiniCssExtractPlugin.loader,
            {
                loader: 'css-loader',
                options: {
                    // El CSS de Leaflet (visor de ruta) apunta a sus imágenes
                    // del control de capas y del marcador por defecto. El visor
                    // no usa ninguno —sus marcadores son propios—, así que esas
                    // URLs no se resuelven ni se empaquetan.
                    url: {
                        filter: (url: string) => !/^images\/(layers|marker-icon|marker-shadow)/.test(url),
                    },
                    modules: {
                        auto: (resPath: string) => Boolean(resPath.includes('.module.')),
                        localIdentName: isDev
                            ? '[path][name]__[local]--[hash:base64:5]'
                            : '[hash:base64:8]',
                    },
                },
            },
            'postcss-loader',
            'sass-loader',
        ],
    };
}
