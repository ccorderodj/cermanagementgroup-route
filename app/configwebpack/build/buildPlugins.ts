import webpack from 'webpack';
import MiniCssExtractPlugin from 'mini-css-extract-plugin';
import { BundleAnalyzerPlugin } from 'webpack-bundle-analyzer';
import ReactRefreshWebpackPlugin from '@pmmmwh/react-refresh-webpack-plugin';
import { BuildOptions } from './types/config';

export function buildPlugins({ isDev }: BuildOptions): webpack.WebpackPluginInstance[] {
    const isProd = !isDev;

    const plugins: webpack.WebpackPluginInstance[] = [
        new webpack.ProgressPlugin(),
        new webpack.DefinePlugin({
            __IS_DEV__: JSON.stringify(isDev),
        }),
    ];

    if (isDev) {
        plugins.push(new ReactRefreshWebpackPlugin());

        // El analizador levantaba un servidor en el 8888 en CADA build de
        // desarrollo, así que dos builds seguidas fallaban con EADDRINUSE y el
        // proceso quedaba escuchando después de terminar. Ahora hay que pedirlo:
        //     ANALYZE=true npm run build:dev
        if (process.env.ANALYZE === 'true') {
            plugins.push(new BundleAnalyzerPlugin({
                openAnalyzer: false,
                analyzerHost: '127.0.0.1',
            }));
        }

        // Se retiró un `ProvidePlugin` que inyectaba jQuery: el proyecto no
        // tiene jQuery entre sus dependencias y nada lo usa.
    }

    if (isProd) {
        plugins.push(new MiniCssExtractPlugin({
            filename: 'css/[name].css',
            chunkFilename: 'css/[name].css',
        }));
    }

    return plugins;
}
